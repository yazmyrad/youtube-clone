# Dev only: the site comes from Vite, with its hot reload WebSocket. No CSP here, because
# Vite's reload preamble is an inline script.
location / {
    set $frontend_upstream http://frontend:5173;
    proxy_pass $frontend_upstream;
    include /etc/nginx/conf.d/proxy_headers.inc;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
}
