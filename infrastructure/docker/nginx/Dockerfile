# nginx + certificat auto-signé généré au build (dev/staging), pour que le
# bloc "listen 443 ssl" de nginx.conf démarre sans configuration
# supplémentaire. En production, monter de vrais certificats sur
# /etc/nginx/certs (ex. Let's Encrypt) : ils remplacent ceux générés ici.

FROM nginx:alpine

RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/privkey.pem \
        -out /etc/nginx/certs/fullchain.pem \
        -subj "/CN=localhost"

EXPOSE 80 443
