#!/bin/sh
set -eu

BACKEND_URL="${VITE_BACKEND_BASE_URL:-http://127.0.0.1:8080}"
FRONTEND_URL="${VITE_FRONTEND_BASE_URL:-http://127.0.0.1:5173}"

escape_sed_replacement() {
  printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

BACKEND_ESCAPED="$(escape_sed_replacement "$BACKEND_URL")"
FRONTEND_ESCAPED="$(escape_sed_replacement "$FRONTEND_URL")"

# Recreate from the pristine build on every container start, so changing runtime
# URLs works after a container recreation and never mutates the image template.
rm -rf /usr/share/nginx/html/*
cp -a /opt/hmsec-dist-template/. /usr/share/nginx/html/

find /usr/share/nginx/html -type f \
  \( -name '*.js' -o -name '*.css' -o -name '*.html' \) |
while IFS= read -r file; do
  sed -i \
    -e "s|__HMSEC_BACKEND_BASE_URL__|${BACKEND_ESCAPED}|g" \
    -e "s|__HMSEC_FRONTEND_BASE_URL__|${FRONTEND_ESCAPED}|g" \
    "$file"
done

exec nginx -g 'daemon off;'
