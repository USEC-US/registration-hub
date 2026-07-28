# AuthState consumer migration design

## Goal

Migrate the first three clear frontend consumers to the tested shared authState: the application shell, account profile page, and sign-in page. The migration removes duplicated current-user/session handling while preserving each page's UI behavior.

## Scope

### Included

- web/src/lib/components/layout/AppShell.svelte
- web/src/routes/account/profile/+page.svelte
- web/src/routes/auth/sign-in/+page.svelte
- Their existing browser-unit tests.

### Excluded

- Registration and payment pages.
- Sign-out behavior and any existing shell link.
- Registration account creation and automatic post-registration sign-in.
- Changes to the AuthState contract, token storage, or server API.

## Component responsibilities

authState remains the application owner of session persistence, current-user state, authentication errors, and redirects.

AppShell calls authState.initialize() on mount and renders authState.status with authState.currentUser. It removes its local currentUser, local account-navigation status, direct account/me request, token lookup, session clearing, and authentication-error helper. Its existing blank account-navigation placeholder continues to cover idle, loading, and unavailable states.

The profile page owns its form fields, saving state, validation errors, and presentation. It uses authState.requireAccessToken() as its entry guard and authState.initialize() as its shared source for initial identity data. Immediately before its raw profile PATCH, it captures an authState session snapshot containing the access token and committed-session generation. After the request succeeds, it updates the shared user cache only when authState accepts that same snapshot as current, preventing a late response from overwriting a newer or signed-out session.

The sign-in page owns form submission, validation errors, and the post-success route. It calls authState.signIn() rather than directly requesting tokens or writing localStorage. It navigates to the sanitized redirect target only when the method returns a user. A null result means the sign-in operation was superseded or user hydration did not complete; the page remains on the form and shows its existing generic sign-in failure.

## Data and error flow

~~~text
AppShell mount
  -> authState.initialize()
  -> shared status and currentUser update account navigation

Profile mount
  -> authState.requireAccessToken()
  -> redirect if missing
  -> authState.initialize()
  -> shared currentUser populates editable fields

Profile save
  -> updateCurrentUser(accessToken, payload)
  -> authState.updateCurrentUser(updatedUser)
  -> shell welcome name updates reactively

Sign-in submit
  -> authState.signIn(email, password)
  -> CurrentUser: navigate to sanitized redirect target
  -> null: remain on form and show generic failure
  -> thrown credential error: preserve field/form error handling
~~~

When profile initialization finishes signed-out after an expired token, the page invokes the shared guard to redirect and presents its existing redirecting UI. On a non-auth current-user failure, it shows the existing profile-load error and does not clear the session. On a profile-save 401 or 403, authState.handleAuthenticationError() clears state and redirects; other errors continue through formErrorsFrom().

AppShell never redirects public pages during initialization. Its failed authentication state simply becomes signed-out.

## Sign-out boundary

The empty, untracked web/src/routes/auth/sign-out/ route was deleted with user authorization before implementation. This migration does not add sign-out behavior or modify any existing shell link.

## Testing and verification

- Update AppShell.svelte.spec.ts to mock the shared state and preserve account-navigation rendering assertions.
- Update auth-pages.svelte.spec.ts to cover profile hydration, profile cache updates, delegated sign-in, post-hydration navigation, and the no-navigation null hydration result.
- Keep auth-state.test.ts as the contract test for AuthState itself.
- Run the focused specs, complete frontend unit suite, pnpm check, and pnpm lint.

## Deferred migration

A later change will adopt the same guard and error-handler APIs in registration, payment, and sign-out flows. Those flows are intentionally untouched here.
