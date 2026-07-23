#!/bin/sh
set -e
export SEARXNG_PORT="${PORT:-8080}"
export SEARXNG_BIND_ADDRESS="${SEARXNG_BIND_ADDRESS:-0.0.0.0}"
if [ -x /usr/local/searxng/dockerfiles/docker-entrypoint.sh ]; then
  exec /usr/local/searxng/dockerfiles/docker-entrypoint.sh "$@"
fi
if [ -x /usr/local/searxng/entrypoint.sh ]; then
  exec /usr/local/searxng/entrypoint.sh "$@"
fi
exec uwsgi --master --http-socket "0.0.0.0:${SEARXNG_PORT}" /usr/local/searxng/searx/uwsgi.ini
