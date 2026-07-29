# Task 6 Report: Protect Public Forms with Turnstile

## Implemented

- Made the Turnstile parameters required for account registration, sign-in, registration submission, and payment-proof uploads.
- Passed the sign-in token through `AuthState.signIn`; `refreshAccessToken` remains unchanged.
- Added `TurnstileWidget` and an empty-token guard to the sign-in, account registration, tournament registration, and visible payment-proof form.
- Passed each action-specific token to its protected request and left forms idle after an early missing-token validation failure.
- After account creation, the automatic sign-in flow now renders a fresh `sign-in` widget token instead of reusing the consumed `account-register` token.

## TDD Evidence

### RED

Before implementation, the focused browser and API suite failed with 15 expected failures: required-token contract assertions showed optional parameters; `AuthState` omitted the token; route tests showed the widget token was neither guarded nor passed; and payment-proof submission lacked the token.

### GREEN

- `pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/api/auth.test.ts src/lib/api/registrations.test.ts src/lib/states/auth-state.test.ts`: passed as part of the focused suite.
- `pnpm exec vitest run src/lib/components/registrations/registration-flow.svelte.spec.ts`: passed as part of the focused suite.
- Combined focused run: 6 files, 70 tests passed.
- `pnpm check`: `svelte-check found 0 errors and 0 warnings`.

## Svelte Autofixer

Ran the official Svelte autofixer on all modified components/routes:

- `web/src/routes/auth/sign-in/+page.svelte`
- `web/src/routes/auth/register/+page.svelte`
- `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- `web/src/lib/components/registrations/PaymentAttemptForm.svelte`

All four runs returned zero issues and required no follow-up invocation.

## Files Changed

- `web/src/lib/api/auth.ts`
- `web/src/lib/api/auth.test.ts`
- `web/src/lib/api/registrations.ts`
- `web/src/lib/api/registrations.test.ts`
- `web/src/lib/states/auth-state.svelte.ts`
- `web/src/lib/states/auth-state.test.ts`
- `web/src/routes/auth/sign-in/+page.svelte`
- `web/src/routes/auth/register/+page.svelte`
- `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- `web/src/routes/auth-pages.svelte.spec.ts`
- `web/src/routes/registration-pages.svelte.spec.ts`
- `web/src/lib/components/registrations/PaymentAttemptForm.svelte`
- `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`
- `.superpowers/sdd/task-5-report.md`
- `.superpowers/sdd/task-6-report.md`

## Self-Review

No blocking findings. The compile-time contract tests require all four public protected API tokens, and the browser tests cover missing-token blocking plus token forwarding. The payment-proof UI is owned by `PaymentAttemptForm.svelte`, rendered from the registration detail route, so it receives the same visible-form protection.

## Concerns

No unresolved concerns.
