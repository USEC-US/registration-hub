#!/bin/sh
set -eu

case "${1:-web}" in
    web)
        shift || true
        cd /app/web

        : "${HOST:=0.0.0.0}"
        : "${PORT:=3000}"
        export HOST PORT

        exec node build/index.js "$@"
        ;;

    api)
        shift || true
        cd /app/server

        : "${HOST:=0.0.0.0}"
        : "${PORT:=8000}"
        : "${FORWARDED_ALLOW_IPS:=*}"

        exec /app/server/.venv/bin/uvicorn \
            config.asgi:application \
            --host "${HOST}" \
            --port "${PORT}" \
            --proxy-headers \
            --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}" \
            "$@"
        ;;

    manage)
        shift
        cd /app/server
        exec /app/server/.venv/bin/python manage.py "$@"
        ;;

    *)
        exec "$@"
        ;;
esac