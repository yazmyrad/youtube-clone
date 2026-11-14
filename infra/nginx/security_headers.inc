# On every response. A location with its own add_header loses the server's, so each such
# location includes this file again.
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
# Playback and thumbnail URLs carry tokens: never hand a page's URL to another site.
add_header Referrer-Policy "same-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
add_header Cross-Origin-Opener-Policy "same-origin" always;
