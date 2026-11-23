#!/usr/bin/env bash
# Dev-сертификаты mTLS для data-service Support Bot (НЕ для прода).
#
#   deploy/certs/generate.sh          # создать то, чего ещё нет
#   deploy/certs/generate.sh --force  # пересоздать всё
#
# Результат — deploy/certs/out/ (в .gitignore). Что есть что — README.md рядом.
set -euo pipefail

OUT="$(cd "$(dirname "$0")" && pwd)/out"
DAYS_CA=3650
DAYS_LEAF=825
SERVER_SAN="DNS:localhost,DNS:support-bot-data,IP:127.0.0.1"

if [[ "${1:-}" == "--force" ]]; then
  rm -rf "$OUT"
fi
mkdir -p "$OUT"
cd "$OUT"

key() {  # key <file>
  [[ -f "$1" ]] || openssl genpkey -algorithm EC \
    -pkeyopt ec_paramgen_curve:P-256 -out "$1" 2>/dev/null
  chmod 600 "$1"
}

ca() {  # ca <name> <CN>
  local name=$1 cn=$2
  [[ -f "$name.crt" ]] && return
  key "$name.key"
  openssl req -x509 -new -key "$name.key" -sha256 -days "$DAYS_CA" \
    -subj "/O=Admin Platform (dev)/CN=$cn" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" \
    -out "$name.crt"
  echo "created CA $name.crt ($cn)"
}

leaf() {  # leaf <name> <CA name> <CN> <extendedKeyUsage> [subjectAltName]
  local name=$1 issuer=$2 cn=$3 usage=$4 san=${5:-}
  [[ -f "$name.crt" ]] && return
  key "$name.key"
  {
    echo "basicConstraints=critical,CA:FALSE"
    echo "keyUsage=critical,digitalSignature,keyAgreement"
    echo "extendedKeyUsage=$usage"
    echo "subjectKeyIdentifier=hash"
    echo "authorityKeyIdentifier=keyid,issuer"
    [[ -n "$san" ]] && echo "subjectAltName=$san"
  } > "$name.ext"
  openssl req -new -key "$name.key" -subj "/O=Admin Platform (dev)/CN=$cn" \
    -out "$name.csr"
  openssl x509 -req -in "$name.csr" -CA "$issuer.crt" -CAkey "$issuer.key" \
    -CAcreateserial -sha256 -days "$DAYS_LEAF" -extfile "$name.ext" \
    -out "$name.crt" 2>/dev/null
  rm -f "$name.csr" "$name.ext"
  echo "created $name.crt ($cn, signed by $issuer)"
}

# 1. Сервер data-service: CA, которому доверяют клиенты (модуль/ядро).
ca server-ca "support-bot-data server CA"
leaf support-bot-data server-ca support-bot-data serverAuth "$SERVER_SAN"

# 2. Доступ к data-service: отдельный CA «admin-access» агента.
#    Любой сертификат от него = право ходить в data-service (решение B).
ca admin-access-ca "support-bot-admin-access"
leaf support_bot-admin-module admin-access-ca support_bot-admin-module clientAuth

# 3. Самопроверка цепочек.
openssl verify -CAfile server-ca.crt support-bot-data.crt >/dev/null
openssl verify -CAfile admin-access-ca.crt support_bot-admin-module.crt >/dev/null
echo "certificates are ready in $OUT"
