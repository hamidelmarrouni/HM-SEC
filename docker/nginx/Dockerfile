FROM nginx:1.27-alpine

COPY gateway.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD wget -q -O - http://127.0.0.1:8080/hmsec-health >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
