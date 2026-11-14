# Shared by the signed media locations. Tokens are in the path, so nothing here is logged.
access_log off;
auth_request /_playback_auth;
limit_except GET {
    deny all;
}
proxy_http_version 1.1;
proxy_set_header Authorization "";
proxy_set_header Cookie "";
# What's behind nginx is nobody's business, and errors must not expose storage's XML.
proxy_hide_header X-Amz-Request-Id;
proxy_hide_header X-Amz-Id-2;
proxy_hide_header X-Ratelimit-Limit;
proxy_hide_header X-Ratelimit-Remaining;
proxy_intercept_errors on;
error_page 400 401 403 404 405 412 416 @media_denied;
error_page 500 502 503 504 @media_unavailable;
include /etc/nginx/conf.d/security_headers.inc;
