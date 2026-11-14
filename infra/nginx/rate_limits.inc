# Per client IP ($binary_remote_addr: nginx sees the client directly). Writes are counted
# only for the method that writes, so reading a video's comments is never limited.
map $request_method $post_client {
    POST    $binary_remote_addr;
    default "";
}

# Guessing passwords: a burst for typos, then one try every 2 seconds.
limit_req_zone $binary_remote_addr zone=login:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=register:10m rate=10r/m;
# Comments and reports.
limit_req_zone $post_client zone=writes:10m rate=20r/m;
# Creating videos and sending their files.
limit_req_zone $post_client zone=uploads:10m rate=10r/m;
# The player's heartbeat: every 10 seconds per tab, so this leaves room for many tabs.
limit_req_zone $post_client zone=views:10m rate=60r/m;

limit_req_status 429;
limit_req_log_level warn;
