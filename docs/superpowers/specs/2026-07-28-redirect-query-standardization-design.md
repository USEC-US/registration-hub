# Redirect query standardization design

## Goal

Use `redirect` as the single frontend query key for an internal destination after sign-in, so every protected route returns users to its original localized pathname, query string, and hash.

## Scope

### Included

- `web/src/lib/states/auth-state.svelte.ts`
- `web/src/routes/auth/sign-in/+page.svelte`
- Every current frontend protected-route redirect producer:
  - `web/src/routes/account/registrations/+page.svelte`
  - `web/src/routes/account/registrations/[id]/+page.svelte`
  - `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- Existing auth-state, authentication-page, registration-page, and navigation tests that assert the query key or post-sign-in destination.

### Excluded

- Backwards compatibility for `redirectTo`; it is removed entirely.
- Authentication token/session behavior, server API, sign-out behavior, and unrelated locale-routing fixes.

## Contract

- Redirect producers construct a localized sign-in URL followed by `?redirect=${encodeURIComponent(currentHref)}`.
- `currentHref` contains the current `pathname`, `search`, and `hash`.
- The sign-in page reads only `page.url.searchParams.get('redirect')`, passes it through `sanitizeInternalRedirect`, and navigates only after `authState.signIn()` returns a user.
- `sanitizeInternalRedirect` remains the open-redirect boundary; missing or invalid destinations use the existing localized registrations fallback.

## Data flow

~~~text
Protected page with missing/expired session
  -> build localized /auth/sign-in?redirect=<encoded pathname+query+hash>
  -> sign-in submits through authState.signIn()
  -> returned user: sanitize redirect and navigate to original internal URL
  -> null/error: remain on form using the existing error behavior
~~~

## Testing and verification

- Change existing AuthState redirect assertions to `redirect`.
- Change existing route redirect assertions to `redirect`.
- Add or update sign-in coverage proving a `redirect` value containing a localized pathname, query, and hash is passed to `goto` after successful hydration.
- Assert `redirectTo` is not accepted by sign-in and therefore uses the safe fallback.
- Run the affected focused specs and `pnpm check`; record the established unrelated locale/env/formatting baseline failures separately.
