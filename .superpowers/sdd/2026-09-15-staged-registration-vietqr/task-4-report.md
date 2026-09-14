# Task 4 implementation report

Branch: `feat/staged-registration-vietqr`, worktree `/tmp/hcmusec-staged-registration`.
Base: `1ded38a`. Scope: browser draft/access storage, observable saved-submission recovery, typed private API clients, and test-fixture compatibility for required lifecycle fields.

## Implementation

- Added strict version-1 draft and saved-access parsing. Drafts use `usec-registration-draft:v1:{gameId}` and expire at seven days. Access records use one key per credential, `usec-registration-access:v1:{credential}`, so one tab cannot replace another tab's list.
- Draft and pending-access payloads accept only staged registration fields. Unknown keys and sensitive legacy/request fields such as payment-intent tokens, proof data, Turnstile/challenge values, and JWT/access-token fields are rejected. Members and institution choices are structurally validated before restoration.
- Pending records require an explicit `actorId`: a positive account ID or `null` guest. Submitted records retain only version, division, credential, state, and registration ID; attempted personal fields and actor metadata are removed after confirmation.
- Credentials use 32 bytes from `crypto.getRandomValues` encoded as exactly 64 lowercase hexadecimal characters.
- Each Storage read, write, enumeration, and removal is contained. `createRegistrationStorage()` wraps an acquired Storage with current-page memory and exposes `persistenceWarning` if acquisition or a later operation fails. `getRegistrationStorage()` is the browser-only shared accessor for both staged and payment routes, preserving memory fallback across client-side `goto` navigation. It returns a fresh fallback during SSR and never retains server-side personal data in module state.
- Added a submission coordinator that saves exact attempted fields before network submission, marks transport failures uncertain, resumes before every replay, and reuses the same credential/payload with a fresh challenge after resume 404. Replays require the original actor. Signed-in attempts without their account session return `account-session-required`; actor mismatch, missing challenge, quota/retry, and payload conflict are distinct observable results.
- A definite 400/422 on the initial prepared request permits editing and removes that prepared access. Once an attempt is uncertain, subsequent resume/replay errors preserve its access and payload; they never authorize a fresh key automatically.
- Added typed clients for staged submit, credential-only resume, scoped payment-session fetch, and scoped multipart proof upload. Credential and JWT authorization are a mutually exclusive TypeScript union for scoped private endpoints.
- Added required lifecycle/payment fields to `PublicTournamentGame` and `RegistrationRead`, plus the complete `RegistrationPaymentSession` and instruction types. Six old test fixtures received real values; no production component was changed.

## Red/green evidence

1. `pnpm exec vitest run --project server src/lib/registrations/browser-storage.test.ts`
   - RED: suite failed because `./browser-storage` did not exist.
   - GREEN: 7 tests passed after initial implementation; final focused suite includes 8 storage tests after current-page quota fallback coverage.
2. `pnpm exec vitest run --project server src/lib/api/registrations.test.ts`
   - RED: four new endpoint tests failed because private client functions did not exist (one fixture scope error was corrected before treating the API failures as valid evidence).
   - GREEN: 8 tests passed after typed client implementation.
3. `pnpm exec vitest run --project server src/lib/registrations/submission.test.ts`
   - RED: suite failed because `./submission` did not exist.
   - A later actor-marker RED produced `storage-unavailable` for actor ID 0 instead of the required `invalid-actor` result.
   - GREEN: final focused suite includes 10 coordinator tests covering pre-request storage, success, uncertainty/resume, resume-404 same-key replay, actor/session guards, first-request validation, unresolved 400/401/409/429 preservation, and quota failure.

Final verification results are appended below after the scoped commit is prepared.

## Exact Task 5 public interfaces

From `browser-storage.ts`:

- `DraftStage = 'details' | 'roster' | 'review'`
- `RegistrationDraft { version: 1; gameId; updatedAt; stage; fields; institutionLabels }`
- `PendingSavedRegistrationAccess { version: 1; gameId; credential; attemptState: 'prepared' | 'uncertain'; registrationId: null; actorId: number | null; submittedPayload }`
- `SubmittedSavedRegistrationAccess { version: 1; gameId; credential; attemptState: 'submitted'; registrationId: number }`
- `readDraft(storage, gameId, now)`, `writeDraft(storage, draft)`, `clearDraft(storage, gameId)`
- `createCredential()`, `saveAccess(storage, entry)`, `listAccess(storage, gameId)`, `forgetAccess(storage, credential)`
- `createRegistrationStorage(acquire?) -> { storage, persistenceWarning }`
- `getRegistrationStorage()` returns the shared browser-lifetime storage/fallback. Task 5 should call this on both registration and payment routes and render `persistenceWarning` when non-null.

From `submission.ts`:

- `submitRegistrationAttempt(RegistrationSubmissionAttemptInput)` creates a new key only for a new user-authorized attempt.
- `recoverRegistrationAttempt(RegistrationRecoveryAttemptInput)` accepts only a pending saved entry; it resumes credential-only first and never creates a key.
- `RegistrationSubmissionResult.status` is `submitted`, `editable`, `uncertain`, `retryable`, `resolution-required`, `account-session-required`, `actor-required`, `challenge-required`, `storage-unavailable`, or `invalid-actor`.
- `submitted` returns either `registration` for submit/replay or `session` for resume, plus the credential. Other results retain the credential and may carry the original error.
- Task 5 supplies `actorId/currentActorId` from initialized `AuthState.currentUser.id`, or explicit `null` guest. It must obtain a fresh Turnstile token only after `challenge-required` or before an eligible resume-404 replay. It must not call a new submission while any unresolved result retains a saved credential.

From `api/registrations.ts`:

- `submitSavedRegistration(accessToken, payload, turnstileToken, credential)`
- `resumeRegistration(credential)`
- `getPaymentSession(id, { accessToken } | { credential })`
- `uploadPaymentProof(id, formData, { accessToken } | { credential })`

Private sessions deliberately allow blank historical bank destination strings and null QR fields while `can_upload_proof` may remain true. There is no message field.

## Dependent Task 5 check work

The accurate `EXPIRED` status union makes three existing status-label switches non-exhaustive. Task 4 did not edit components. Task 5 must add localized expired display behavior at:

- `web/src/lib/components/registrations/StatusTimeline.svelte:14`
- `web/src/routes/account/registrations/+page.svelte:41`
- `web/src/routes/account/registrations/[id]/+page.svelte:44`

Until those component changes land, `pnpm check` reports exactly these three errors and zero warnings. The six incomplete test fixtures exposed by guaranteed payment fields were updated rather than weakening the API types.

The complete Node Vitest project retains the documented baseline auth SSR failures: 126 passed, 2 failed in `src/routes/auth-pages.test.ts` because direct `svelte/server.render` lacks SvelteKit `page` context. Task 4's focused suites pass and do not touch that path.

## Final verification

- `pnpm exec vitest run --project server src/lib/registrations/browser-storage.test.ts src/lib/registrations/submission.test.ts src/lib/api/registrations.test.ts`: **3 files, 26 tests passed**.
- `pnpm exec vitest run --project server`: **19 files/126 tests passed; 1 file/2 known auth SSR tests failed** with the baseline missing SvelteKit `page` context described in `environment.md`.
- Scoped `pnpm exec eslint` over all 13 changed TypeScript/Svelte test files: **exit 0, no findings**.
- Scoped `pnpm exec prettier --check` over the same files: **all files matched**.
- `pnpm check`: i18n passed, then Svelte check reported **exactly 3 errors and 0 warnings**, all three Task 5-owned `EXPIRED` label switches listed above.
- `git diff --check`: clean before staging.

The root-owned plan edit remains unstaged and excluded from the Task 4 commit.

## Review fix round 1

Addressed all findings in `task-4-review.md`:

- Draft parsing now accepts the roster editor's structurally valid blank `institution_label` placeholder, so incomplete roster progress round-trips. Pending/uncertain access parsing continues to require a nonblank institution choice before a submission can be retained or replayed.
- The resilient Storage wrapper now mirrors successful primary reads. If a later quota/security failure disables primary storage, entries already observed during the browser lifetime remain available from current-page memory. While primary storage is healthy, reads and complete key enumeration treat it as authoritative, update cached values, and invalidate cached keys removed by another tab.
- New submission attempts enforce the actor/session pair before persistence or network access: positive account actors require an access token, and explicit guests reject a supplied account token. This complements the existing resume-first recovery guard.
- Recovery coverage now distinguishes uncertain replay 400/422 from first-attempt editable validation errors and verifies `challenge-required` before replay.
- Added `findSubmittedAccess(storage, registrationId)`, which enumerates and strictly parses saved access records before returning a submitted credential. The payment route can resolve its credential from the registration ID without duplicating raw JSON parsing or carrying division state in the URL.

TDD and verification evidence:

- RED: `pnpm exec vitest run --project server src/lib/registrations/browser-storage.test.ts src/lib/registrations/submission.test.ts` — 22 passed, 4 failed. Failures were the incomplete draft, observed-access fallback, signed-in actor without token, and guest actor with token.
- GREEN: the same command — **2 files, 26 tests passed**.
- `pnpm check` — the fixes add no diagnostics; output remains exactly the three Task 5-owned non-exhaustive `EXPIRED` label errors and zero warnings.
- Initial scoped ESLint found one test-only unused destructured field while constructing the incomplete member fixture; the fixture was rewritten with explicit real values before final verification.
- Additional payment-route lookup RED: the focused storage suite failed 1 of 12 tests because `findSubmittedAccess` did not exist; the implementation reuses the same allowlisted access enumeration/parser.
- Final affected verification: `pnpm exec vitest run --project server src/lib/registrations/browser-storage.test.ts src/lib/registrations/submission.test.ts` — **2 files, 27 tests passed**. Scoped ESLint exited 0 and scoped Prettier reported all four files matched.
