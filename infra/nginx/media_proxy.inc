# Shared by the signed media locations. Tokens are in the path, so nothing here is logged.
access_log off;
auth_request /_playback_auth;
limit_except GET {
    deny all;
}
include /etc/nginx/conf.d/storage_proxy.inc;
error_page 400 401 403 404 405 412 416 @media_denied;
error_page 500 502 503 504 @media_unavailable;
include /etc/nginx/conf.d/security_headers.inc;
