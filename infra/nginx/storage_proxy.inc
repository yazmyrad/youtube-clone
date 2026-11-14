# Shared by every location that reads from storage. What's behind nginx is nobody's business:
# storage's request ids and its own security headers stay out (nginx sets the real ones, once).
proxy_http_version 1.1;
proxy_set_header Authorization "";
proxy_set_header Cookie "";
proxy_hide_header X-Amz-Request-Id;
proxy_hide_header X-Amz-Id-2;
proxy_hide_header X-Ratelimit-Limit;
proxy_hide_header X-Ratelimit-Remaining;
proxy_hide_header Strict-Transport-Security;
proxy_hide_header X-Content-Type-Options;
proxy_hide_header X-Xss-Protection;
proxy_hide_header Vary;
# Errors must not expose storage's XML.
proxy_intercept_errors on;
