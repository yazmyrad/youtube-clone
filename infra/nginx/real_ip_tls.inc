# `--domain` mode only, mounted by compose.domain.yaml: the client's address comes from
# Caddy, which sits in front and sets X-Forwarded-For. Trusted from Caddy's fixed address
# alone, so nobody else can choose their own address for rate limits and view counting.
set_real_ip_from 10.213.67.2;
real_ip_header X-Forwarded-For;
real_ip_recursive off;
