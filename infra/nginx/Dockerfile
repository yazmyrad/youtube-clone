FROM nginxinc/nginx-unprivileged:1.30.6-alpine

COPY default.conf proxy_headers.inc media_proxy.inc /etc/nginx/conf.d/
COPY html/ /usr/share/nginx/html/
