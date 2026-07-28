# Shared AuthState design

## Goal

Create a single client-side, reactive authority for the authenticated session and current user. It will remove duplicated current-user loading and authentication redirect logic when consumers are migrated in later work.

This increment establishes and tests the state layer only. It does not migrate any component or route.

## Scope

### Included

- A singleton `AuthState` class in `web/src/lib/auth/auth-state.svelte.ts`.
- Reactive `currentUser` and session status.
- Session restoration, sign-in, sign-out, access-token refresh, current-user loading, and current-user updates.
- A client-side guard that redirects missing or invalid sessions to the localized sign-in page while preserving the attempted URL in `redirectTo`.
- Central recognition and handling of API `401` and `403` errors.
- Focused automated tests for the new state layer.

### Excluded

- Migrating `AppShell`, the profile page, registration pages, payment callbacks, or the existing sign-out route to `AuthState`.
- Changing registration UI or moving `registerAccount` into `AuthState`.
- Changing the server authentication API or token-storage mechanism.
- Altering existing uncommitted work.

## Architecture

`AuthState` is a singleton class exported by an `.svelte.ts` module so its fields can use Svelte 5 runes and remain reactive wherever the instance is imported.

```text
Components and route handlers
            |
            v
        AuthState
   /        |         \
session.ts  api/auth.ts  auth/navigation.ts
```

`api/auth.ts` remains a thin HTTP layer. `session.ts` remains responsible only for localStorage persistence. `AuthState` coordinates those modules and owns the application-level session lifecycle.

The exported class has these reactive fields:

- `currentUser: CurrentUser | null`
- `status: 'idle' | 'loading' | 'signed-in' | 'signed-out' | 'unavailable'`

The public API consists of:

- `initialize()` to restore the locally persisted session and load `/account/me/` once.
- `signIn(email, password)` to request tokens, persist them, then hydrate `currentUser`.
- `signOut()` to clear token storage and reactive auth state.
- `refreshSession()` to replace the access token while retaining the refresh token.
- `updateCurrentUser(user)` to replace the cached user after an account update.
- `requireAccessToken()` to enforce a protected client route.
- `handleAuthenticationError(cause)` to centralize `401` and `403` behavior and tell callers whether it handled the error.

`registerAccount` remains in `api/auth.ts`. Registration is an account-provisioning flow that currently does not establish a session; keeping it outside `AuthState` preserves freedom for future custom onboarding steps.

## Client and SSR boundary

The singleton begins with inert state (`idle` and `null`). All localStorage access, API calls, and navigation are browser-only. No server-side request may populate or mutate the singleton with user information, preventing cross-request state leakage.

## Data and error flow

`initialize()` is the user-cache operation. When there is no access token, it sets `signed-out` without an API request. With a token, it loads `/account/me/`; concurrent calls share one in-flight request.

`requireAccessToken()` is deliberately a token guard rather than a user-profile guard. If there is no token, it redirects using the existing replace-navigation helper to the localized sign-in route, with the current pathname, query string, and fragment encoded in `redirectTo`. If a token exists, it returns that token without requiring `/account/me/` to be reachable. This preserves the current behavior of protected pages.

When a protected API call fails with `401` or `403`, the caller passes the error to `handleAuthenticationError()`. The method clears stored credentials and reactive user state, redirects to sign-in with `replace`, and returns `true`. Other errors return `false`, allowing the page that owns the UI to render its existing error message.

Non-auth errors while loading the current user set `status` to `unavailable`. They do not clear tokens or redirect.

`signIn()` stores the returned token pair and hydrates the user state. `signOut()` clears both persistence and reactive state. `refreshSession()` updates only the access token, retaining the refresh token.

## Testing and verification

New focused tests will define the class contract before production implementation. They will verify:

- session restoration with no token, a valid token, an invalid token, and an unavailable current-user endpoint;
- concurrent initialization triggers one current-user request;
- sign-in persists tokens and hydrates current-user state;
- sign-out clears storage and reactive values;
- refresh retains the refresh token and replaces the access token;
- the guard produces the localized sign-in URL with the current URL as `redirectTo`; and
- `401` and `403` clear and redirect, while unrelated errors remain unhandled.

Before the foundation is considered ready, run the focused tests, the full frontend unit suite, `pnpm check`, and the frontend formatting and lint checks.

## Deferred migration

A later, separately reviewed change will migrate existing consumers in stages: first `AppShell` and the profile page, then the protected registration pages, payment-auth callbacks, and sign-out flow. That migration will use the tested `AuthState` API and preserve each page's loading and non-auth error UI.
