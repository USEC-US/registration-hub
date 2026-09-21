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
- `POST /api/registrations/*/payment-attempts/` (legacy)
- `POST /api/registrations/resume/`
- `POST /api/registrations/*/payment-session/`
- `POST /api/registrations/*/payment-proof/`
- `POST /api/payment-references/` (legacy issuance)

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

## Application limits and remaining deployment work

Private resume/payment-session reads have a 120/hour per-client-IP Django throttle; private proof uploads have a separate 30/hour throttle. Legacy reference issuance is also throttled at 30/hour. These use the configured Django cache, so deployment must not assume process-local counters provide a shared multi-worker limit. Redis-backed shared counters remain deferred until a production cache is provisioned. Keep the edge/origin limits above; application throttles do not replace them.

Do not log `X-Registration-Access`, authorization headers, or private session bodies. Preserve `private, no-store` on success and error responses. Forward the dedicated access header to Django without placing it in a URL.
