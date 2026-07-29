# Account Identity and Security Foundation Design

## Purpose

Phase 1 makes accounts, identity, and public self-service actions predictable
enough to support the rest of the tournament portal. This phase completes the
visible logout path, restores the institution catalogue work, standardizes
protected-page behavior, adds Turnstile to public self-service forms, and
documents the rate-limit deployment posture for a split frontend/backend
release.

This design extends the existing account-institution catalogue design instead
of replacing it. The July 22 catalogue model remains the account data direction;
this document adds the authentication, Turnstile, and deployment-security
decisions needed to execute Phase 1 as one coherent slice.

## Goals

- Expose logout clearly in the authenticated application shell.
- Make login, logout, expired sessions, redirects, and protected pages behave
  consistently for participants and organizers.
- Replace account-level free-text `school` with the shared institution catalogue
  described in `2026-07-22-account-institution-design.md`.
- Keep account identity separate from tournament-specific roles. Captain,
  manager, roster member, entrant, and result behavior remain registration or
  competition data, not persistent account roles.
- Guard every public self-service form with Cloudflare Turnstile:
  account registration, sign-in, tournament registration submission, and manual
  payment proof submission.
- Keep Turnstile secrets out of browser code.
- Allow local development to continue when Turnstile keys are missing, with
  clear developer warnings.
- Fail loudly outside development if required Turnstile environment variables
  are missing.
- Document Cloudflare WAF and NGINX rate limiting as the production defense
  layer after domains and hosting are final.

## Non-goals

- Building a frontend organizer/admin panel.
- Implementing Redis or application-level distributed rate limiting in this
  phase.
- Creating Cloudflare WAF rules, Worker rate-limit bindings, DNS records, or
  NGINX production config before deployment domains are chosen.
- Adding account-wide tournament-specific roles.
- Changing the registration captain/manager model before the registration-flow
  phase.
- Implementing SePay, brackets, Channels, TFT, Round Robin, or Swiss.

## Current Surface

The backend is Django and DRF under `/api/`. The current relevant endpoints are:

| Endpoint | Current purpose | Phase 1 protection |
| --- | --- | --- |
| `POST /api/auth/register/` | Create account | Turnstile required outside dev passthrough |
| `POST /api/auth/token/` | Sign in with email/password | Turnstile required outside dev passthrough |
| `POST /api/auth/token/refresh/` | Refresh JWT access token | No Turnstile; authenticated token lifecycle |
| `GET/PATCH /api/account/me/` | Current account profile | Authenticated; institution input after catalogue migration |
| `POST /api/registrations/submit/` | Submit tournament registration | Turnstile required outside dev passthrough |
| `POST /api/registrations/{id}/payment-attempts/` | Submit manual payment proof | Turnstile required outside dev passthrough |

The frontend is SvelteKit 2/Svelte 5. Auth state already lives in
`web/src/lib/states/auth-state.svelte.ts`. The application shell reads that
state, but the current signed-in navigation does not visibly expose logout.
There is an untracked empty `/auth/logout` route in the worktree; Phase 1 should
either implement it or remove it as part of the explicit logout design, not
leave it as a route stub.

## Design Overview

### Account and Session Behavior

The shared `authState` remains the browser authority for current-user state,
token storage, sign-in, sign-out, and redirect behavior. Protected frontend
pages should call shared auth-state guard methods rather than duplicating
session clearing and sign-in URL construction.

Logout is a visible authenticated-shell action. Activating it clears local
tokens, resets shared auth state, and lands the user on a localized public page
with a clear signed-out status. It does not need a backend API call while JWT
refresh tokens are client-held and not server-revoked.

Auth expiry and unauthorized API responses use one shared pattern:

1. Detect `401` or `403` from authenticated APIs.
2. Clear local session state.
3. Redirect to localized sign-in with a sanitized internal redirect target.
4. Show a short loading or redirecting state while navigation happens.

Public shell initialization must never redirect a public page. Redirects belong
to protected pages and protected actions.

### Institution Catalogue

The institution catalogue follows
`docs/superpowers/specs/2026-07-22-account-institution-design.md`.

The account model changes from `User.school` to `User.institution`, a nullable
database relation for migrated legacy users and a required field for new
self-service account creation and completed profile updates. Existing non-empty
school text migrates to shared custom pending institution records. Empty legacy
values remain empty until the account holder next completes an institution
selection.

The account API accepts exactly one of:

- `institution_id` for a verified catalogue record; or
- `institution_label` for a custom non-empty label that resolves or creates a
  shared pending record.

The search endpoint is public and read-only:

```text
GET /api/institutions/?q=<text>
```

It returns a limited result set from server-side catalogue search. The browser
must not ship the full `server/university.json` dataset.

Registration roster institution/school snapshots stay independent. The account
institution can help identify the authenticated actor, but it does not overwrite
team roster fields and does not become a player eligibility proof.

### Turnstile App Contract

Turnstile is an application-level guard for public self-service forms. The
browser renders a reusable Svelte component and submits the resulting token to
the existing backend action. The backend verifies that token with Cloudflare
Siteverify before running the existing action logic.

Environment variables:

| Variable | Owner | Visibility | Required behavior |
| --- | --- | --- | --- |
| `PUBLIC_TURNSTILE_SITE_KEY` | SvelteKit frontend | Public browser value | Required outside dev |
| `TURNSTILE_SECRET_KEY` | Django backend | Private server value | Required when `DEBUG=False` |

The secret key must only be imported or read in server-only backend code. The
frontend never calls Siteverify and never receives `TURNSTILE_SECRET_KEY`.

Development behavior:

- If either key is missing in local development, the protected form remains
  usable.
- The frontend component renders a developer-facing warning where the widget
  would appear.
- The backend verification helper logs or returns a structured dev bypass
  result.
- Tests cover the bypass so it is intentional, not accidental.

Production behavior:

- The SvelteKit build fails if a protected form can render without
  `PUBLIC_TURNSTILE_SITE_KEY`.
- Django startup/checks fail when `DEBUG=False` and `TURNSTILE_SECRET_KEY` is
  missing.
- Protected backend endpoints reject missing, invalid, expired, or replayed
  Turnstile tokens before running their existing action.

Reusable frontend component:

```text
web/src/lib/components/forms/TurnstileWidget.svelte
```

The component owns script loading, widget rendering, success token capture,
expiry/reset, error state, and dev-warning display. Forms consume it through a
small local state contract:

```typescript
type TurnstileState = {
  token: string;
  verifiedForAction: string;
};
```

Each protected API client adds `turnstile_token` to JSON payloads or appends it
to `FormData` for uploads. The component should include an action value such as
`sign-in`, `account-register`, `registration-submit`, or `payment-proof-submit`
so the backend can compare the expected action when Siteverify returns one.

Backend verification lives behind a small service boundary, for example:

```text
server/config/turnstile.py
```

The service returns a typed result rather than raising raw HTTP exceptions from
deep inside form logic. DRF views call it at the start of protected actions.
Verification uses Cloudflare Siteverify over HTTPS, sends the secret and
response token, and treats `timeout-or-duplicate` as a user-retry case.

### Rate Limiting and WAF

Turnstile is not the whole abuse story. Phase 1 implements Turnstile in app
code and documents rate limiting for production. The actual Cloudflare and
NGINX rules should be applied when final hostnames are known.

Recommended deployment shape:

```text
Browser
  -> Cloudflare-proxied frontend host
  -> Cloudflare-proxied API host or Cloudflare Tunnel
  -> NGINX on VPS
  -> Django ASGI/WSGI application
```

If the API host is not proxied through Cloudflare, Cloudflare WAF and rate
limiting cannot protect backend requests. In that case, NGINX and Django are
the backend protection layers.

Cloudflare controls to plan:

- WAF Rate Limiting Rules for sensitive POST endpoints.
- Managed WAF rules for general exploit protection.
- Origin protection through Cloudflare Tunnel, or proxied DNS plus origin
  firewall allowlisting and optionally Authenticated Origin Pulls.

NGINX controls to plan:

- Restore real visitor IP from `CF-Connecting-IP` only for trusted Cloudflare
  source ranges.
- Apply `limit_req_zone` and `limit_req` to sensitive API locations.
- Return `429` for rate-limited requests.
- Keep upload body limits explicit for payment proof endpoints.

Initial sensitive endpoint set for edge and origin rate limits:

- `POST /api/auth/token/`
- `POST /api/auth/register/`
- `POST /api/registrations/submit/`
- `POST /api/registrations/*/payment-attempts/`

Redis-backed application rate limits are deferred until Redis already exists
for Channels or another production runtime need.

### Permissions

Phase 1 verifies the current permission boundaries rather than inventing
tournament-specific account roles.

- Participants can access only their own submitted registrations through the
  self-service API.
- Staff access to Django Admin tournament objects remains group-gated through
  the existing organizer staff policy until the organizer tools phase builds a
  stronger workflow.
- API schema/docs stay debug-or-staff only.
- Private account fields such as `student_id`, private contact details, and
  payment evidence are not exposed through public pages.

The account institution is not an authorization grant. A user from a verified
institution does not automatically become eligible for a tournament, and a
pending custom institution does not block basic account use.

## Testing Strategy

Backend tests should cover:

- Registration and sign-in reject missing or invalid Turnstile tokens when
  `DEBUG=False`.
- The same endpoints bypass Turnstile in `DEBUG=True` with missing keys.
- The Siteverify service maps success, invalid token, timeout/duplicate, and
  network failure to stable API responses.
- Protected registration and payment actions do not call their existing service
  functions until Turnstile verification succeeds.
- Institution import, search, custom resolution, and account serializer behavior
  from the existing catalogue plan.
- Permission boundaries for participant registration reads and staff-only
  surfaces.

Frontend tests should cover:

- `TurnstileWidget` renders a widget when the site key exists.
- `TurnstileWidget` renders a dev warning when the site key is absent in dev.
- Protected forms include `turnstile_token` before calling their API clients.
- Sign-in stays on the form when Turnstile has not produced a usable token.
- Logout is visible for signed-in users and clears shared auth state.
- Institution combobox search, keyboard selection, free-text fallback, and
  account page integration.

Verification commands should include focused backend test modules, focused
Vitest suites for auth/account/registration components, `pnpm check`,
`uv run python manage.py check`, and migration dry-run checks.

## External References

- Cloudflare Turnstile server-side validation:
  https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- Cloudflare Turnstile client-side rendering:
  https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/
- Cloudflare WAF rate limiting rules:
  https://developers.cloudflare.com/waf/rate-limiting-rules/
- Cloudflare rate limiting best practices:
  https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/
- Cloudflare Tunnel:
  https://developers.cloudflare.com/tunnel/
- Cloudflare authenticated origin pulls:
  https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/explanation/
- NGINX request rate limiting:
  https://docs.nginx.com/nginx/admin-guide/security-controls/controlling-access-proxied-http/
- SvelteKit environment variables and server-only modules:
  https://svelte.dev/docs/kit/environment-variables
  https://svelte.dev/docs/kit/server-only-modules

## Open Deployment Decisions

- Final frontend hostname.
- Final API hostname and whether it is proxied through Cloudflare, served
  through Cloudflare Tunnel, or exposed directly.
- Production NGINX layout and whether it terminates TLS itself or sits behind
  a tunnel.
- Exact WAF rate thresholds after beta traffic is known.

These decisions should not block local app implementation. They do block
claiming production readiness.
