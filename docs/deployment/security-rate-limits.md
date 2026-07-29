# Security Rate Limits

## Deployment Boundary

Cloudflare WAF and rate limiting protect the backend only when API traffic
passes through a Cloudflare-proxied hostname or Cloudflare Tunnel. If clients
can reach the VPS origin directly, NGINX and Django remain the only backend
protections for those direct requests.

## Sensitive POST Endpoints

- `POST /api/auth/token/`
- `POST /api/auth/register/`
- `POST /api/registrations/submit/`
- `POST /api/registrations/*/payment-attempts/`

## Cloudflare Plan

Create WAF Rate Limiting Rules for the sensitive POST endpoints after final
frontend and API hostnames are selected. Start with conservative thresholds
during beta, monitor false positives, and tighten after real traffic is known.
Use managed WAF rules for generic exploit protection.

## Origin Plan

Configure NGINX `limit_req_zone` and `limit_req` for the same endpoint groups.
Trust `CF-Connecting-IP` only from published Cloudflare source ranges. Return
`429` for rate-limited requests and keep payment-proof upload body limits
explicit.

## Deferred App Limits

Redis-backed Django rate limits are deferred until Redis exists for Channels or
another production runtime need.
