#!/bin/sh
set -eu

umask 077

if [ -z "${AIOA_OPERATOR_TOKEN:-}" ]; then
    printf '%s\n' 'AIOA operator token missing' >&2
    exit 2
fi

if [ -z "${AIOA_LOCAL_API_TOKEN_PATH:-}" ]; then
    printf '%s\n' 'AIOA local API token path missing' >&2
    exit 2
fi

printf '%s\n' "$AIOA_OPERATOR_TOKEN" > "$AIOA_LOCAL_API_TOKEN_PATH"
chmod 0600 "$AIOA_LOCAL_API_TOKEN_PATH"
unset AIOA_OPERATOR_TOKEN

exec python -m aioa_cloudops_agent.portable_server
