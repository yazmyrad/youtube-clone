# The built SPA. Unknown paths get index.html, so the client router can handle them.
location / {
    root /usr/share/nginx/html;
    try_files $uri /index.html;
}

# The icon is /favicon.svg. Without this, the fallback would answer with the page.
location = /favicon.ico {
    return 404;
}

# Revalidated on every load, so a deploy reaches browsers at once.
location = /index.html {
    root /usr/share/nginx/html;
    add_header Cache-Control "no-cache" always;
    add_header X-Content-Type-Options "nosniff" always;
    # blob: is what hls.js needs, for its media source and its worker.
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" always;
}

# File names carry a content hash. A missing one is a real 404: answering with index.html
# would hand the browser HTML where it expects a script.
location /assets/ {
    root /usr/share/nginx/html;
    try_files $uri =404;
    add_header Cache-Control "public, max-age=31536000, immutable";
    add_header X-Content-Type-Options "nosniff" always;
}
