# Consolidated final-review fix wave

Started from `eff4b01` in the isolated feature worktree. The user then merged the feature and explicitly required direct work on `main`; the controller transferred the uncommitted patch to `/home/nhqthang/Documents/codes/hcmusec-tnmt-registration`, base `d3c545d`. No further temporary-worktree mutations occurred. Scope: Important I1 and Minor 1–3 from `final-review.md`, plus the user-reported incorrect unavailability message. Final review checkbox remains unchecked for the controller's scoped approval.

## Implementation and decisions

- The actual keyed registration route/Wizard reads the division-scoped legacy `sessionStorage` quote before offering a fresh form. English/Vietnamese guidance directs already-paid participants to organizers with proof; the unpaid choice is explicit and belongs only to the mounted division. Ordinary staged requests still omit proof and payment-intent tokens.
- The old token survives validation failures and uncertain results. The originating Wizard associates the explicitly chosen fresh attempt with its credential, and clears only a matching old token on that attempt's confirmed success, including same-instance lost-response resume. Late results remain bound to the original division; a newer token is never removed.
- Saved-entry recovery can resume a committed entry without an unpaid declaration. `allowReplay: false` stops after a missing-entry response; it cannot issue a fresh submission. Reload/navigation does not persist the unpaid declaration or attempt association. Therefore read-only resume after reload conservatively preserves the old token; unrelated saved-entry recovery also preserves it. An explicitly chosen replay with a successful receipt can clear its matching token. If that replay itself loses its response, subsequent resume conservatively retains the token: the controller explicitly accepted retaining this edge rather than adding cleanup metadata/callbacks. No persistent migration metadata was added.
- Payment receipt state uses already-prefetched payment objects; unprefetched service locks still query fresh database state. A four-entry account response is bounded to four queries overall and one payment prefetch, including overdue/protected cases. Upload, rejection/replacement, and verification regressions exercise fresh service state.
- QR boundary coverage decodes top-level TLV and nested `62/08`, rather than searching for digits anywhere in the payload. Valid account/amount digits `62` reproduce the old test bug.
- Disposable fixture creation uses `os.open(O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)`. Existing regular files and symlinks are rejected without overwrite; failed new writes remove their partial file. Harness teardown only removes the fixture returned by successful creation. No normal database migration/seed or production receiving settings were changed.

## User-reported availability message

The controller verified that local `test-open-tournament`, division 3, was open with future registration close and unlimited capacity, but `payment_available=false` because payment settings were absent. The Wizard previously combined schedule, capacity, and payment readiness into one boolean and displayed the generic `stages_closed` message for every failure.

The Wizard now derives a reason using server `registration_state` (`not_open`, `closed`, `full`), remaining capacity, and payment availability. An open paid division without payment readiness says **Payment is not ready for this division. Please contact the organizers before registering.** English and Vietnamese copies are provided. Free registration remains available without payment setup. Saved access and draft restoration retain their existing precedence. The backend payment guard, dates, and receiving settings were not changed.

RED on main: `PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run src/routes/registration-stages.svelte.spec.ts -t 'explains availability|explains payment availability'` failed six assertions with the previous generic message; `/tmp/hcmusec-main-availability-red.log`, 4.17s. Added tests cover not-open/closed/full server states, zero remaining capacity, open paid payment-not-ready, Vietnamese guidance, free-entry continuity, and saved access/draft restoration.

GREEN on main: `PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run src/routes/registration-stages.svelte.spec.ts src/lib/registrations/submission.test.ts` passed **47/47**, two files, 19.15s; `/tmp/hcmusec-main-route-green.log`. This includes the final conservative lost-replay parameter and all original route/submission regression cases.

## TDD evidence

Backend RED (from `server/`):

```sh
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test registrations.tests.test_reservations.ReceiptQueryTests registrations.tests.test_e2e_fixture registrations.tests.test_vietqr --keepdb --noinput
```

`/tmp/hcmusec-final-backend-red.log`: expected failures: receipt payment queries **9 != 1**; QR substring assertion incorrectly finds `62` in a valid account and amount; new fixture test imports the not-yet-created `e2e.fixtures` helper. 11 tests, two failures/one import error.

Backend GREEN:

```sh
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test registrations.tests.test_reservations registrations.tests.test_e2e_fixture registrations.tests.test_vietqr --keepdb --noinput
```

`/tmp/hcmusec-final-backend-green.log`: **28 passed**, 9.671s, Django system check clean.

Route RED (from `web/`):

```sh
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run src/routes/registration-stages.svelte.spec.ts -t 'legacy|unpaid decision|read-only recovery'
```

`/tmp/hcmusec-final-route-red.log`: **six failed**, 16 skipped, because the real route has no legacy guidance/unpaid control. These mount `RegisterPage`, not the retained orphan `TransferContentField`.

Route GREEN:

```sh
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run src/routes/registration-stages.svelte.spec.ts src/lib/registrations/submission.test.ts
```

`/tmp/hcmusec-final-route-green.log`: **38 passed**, two files, 17.73s. Intermediate fixture fixes reset resume mock counts per test and remove an optional draft from the specific missing-replay test so its Turnstile view is deterministic. Those intermediate repairs changed test isolation/timing only.

Exact covering test names in `registration-stages.svelte.spec.ts`:

- `guards the real route with organizer guidance before any fresh submission and retains failed legacy replacement`
- `clears only the old division token after the explicit fresh flow succeeds without sending old proof or token`
- `does not carry an unpaid decision across reload or division navigation`
- `retains an uncertain legacy flow until confirmed recovery, with reload=%s` (false and true)
- `allows read-only recovery but guards a missing submission replay after reload, lost replay=%s` (false and true)
- `does not erase a changed legacy token when the explicitly chosen submission finishes`
- `retains an old quote when an unrelated saved entry resumes even after an unpaid choice`

The preexisting ordinary flow test now explicitly asserts absence of `payment_intent_token` and `proof_file`.

Backend tests: `ReceiptQueryTests.test_multi_entry_account_receipts_use_one_payment_prefetch`, `ReceiptQueryTests.test_service_state_is_fresh_after_upload_reject_and_replacement`; `PrivateFixtureTests.test_file_is_private_at_creation_even_with_permissive_umask`, `test_preexisting_file_and_symlink_are_never_followed_or_overwritten`, `test_failed_write_removes_only_its_new_file`; amended `VietQrTests.test_content_boundary_is_exact_and_long_content_is_omitted`.

Real browser regression: `migrated payment quote requires an unpaid choice and survives a lost response until confirmed recovery`. It creates a real unattached quote through the retained API, sets the old browser token, submits through the route after the explicit choice, drops the real Django response, resumes the committed entry, and verifies the old server quote still resolves.

## Final verification

Frontend commands are sequential to avoid shared generated-artifact races. Full Django and Vitest regressions ran once on the completed four-finding fix before the later authorized availability-only UI edit. The unchanged backend evidence is retained. The later conservative lost-replay test and availability-only UI change receive focused route/submission verification on main rather than repeating the full suites.

| Directory | Exact command                                                                                                                                                                                                                               | Result / log                                                  |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| server    | `TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test --keepdb --noinput`                                                                                                                                                     | 253 passed, 121.678s; `/tmp/hcmusec-final-django.log`         |
| server    | `TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py makemigrations --check --dry-run`                                                                                                                                            | No changes detected; `/tmp/hcmusec-final-migrations.log`      |
| server    | `TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py check`                                                                                                                                                                       | No issues; `/tmp/hcmusec-final-system-check.log`              |
| server    | `.venv/bin/ruff check .`                                                                                                                                                                                                                    | All checks passed; `/tmp/hcmusec-final-ruff.log`              |
| web       | `pnpm check`                                                                                                                                                                                                                                | 0 errors/0 warnings; `/tmp/hcmusec-final-web-check.log`       |
| web       | `PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run`                                                                                                                                                                     | 300 passed, 40 files, 39.64s; `/tmp/hcmusec-final-vitest.log` |
| web       | `pnpm exec eslint src/lib/components/registrations/RegistrationWizard.svelte src/lib/registrations/submission.ts src/routes/registration-stages.svelte.spec.ts e2e/django/registration.spec.ts`                                             | Passed; `/tmp/hcmusec-final-eslint.log`                       |
| web       | `pnpm exec prettier --check src/lib/components/registrations/RegistrationWizard.svelte src/lib/registrations/submission.ts src/routes/registration-stages.svelte.spec.ts e2e/django/registration.spec.ts messages/en.json messages/vi.json` | Passed; `/tmp/hcmusec-final-prettier.log`                     |

Expected negative-request/backend injected-failure logging and existing generated SvelteKit/Paraglide diagnostics are not hidden.

## Self-review and constraints

Reviewed the implementation diff against the four findings and the shared contract. No new model/schema, payment rail, bank configuration, secret URL, production hook, proof transport, or public serializer identity changes. The later user-reported availability fix changes only the participant-facing reason while preserving the same payment-readiness guard. The reported local paid division therefore remains blocked until organizers supply valid payment settings; no receiving destination is invented by this fix. Existing account and guest flows retain their behavior. The only recovery API-client option is an explicit replay boundary, leaving default recovery behavior unchanged elsewhere.

Conservative limitation: after reload the old token can remain even after a committed fresh entry is recovered, because no persisted association proves that this is the quote's replacement. An explicitly allowed replay whose own response is lost also conservatively retains the old token after later resume. The controller accepted both preservation cases, including the cost that an old-session warning can recur. This is intentional and documented; saved submitted access remains usable, and a possible earlier transfer is never silently dismissed. Existing mobile header/tooling limitations and operational bank-app/scheduler acceptance gates remain outside this wave.

Initial restricted test attempts could not reach PostgreSQL or pnpm's cache; approved escalation resolved those environment prerequisites. Two edit commands used a workspace-relative path from `web/` and failed before mutation; rerun with an absolute path succeeded. No dependency installation or environment-file edits.

## Files changed

- `web/src/lib/components/registrations/RegistrationWizard.svelte`, `web/src/lib/registrations/submission.ts`, `web/messages/{en,vi}.json`: migration guard, recovery replay boundary, localized guidance.
- `web/src/routes/registration-stages.svelte.spec.ts`, `web/e2e/django/registration.spec.ts`: actual route/component and real Django migration regressions.
- `server/registrations/reservations.py`, `server/registrations/tests/test_reservations.py`: receipt query reuse and fresh service state tests.
- `server/registrations/tests/test_vietqr.py`: TLV boundary assertions.
- `server/e2e/fixtures.py`, `server/e2e/serve.py`, `server/registrations/tests/test_e2e_fixture.py`: secure exclusive fixture creation and teardown/filesystem tests.
- `docs/payments/payment-references.md`, `docs/testing/registration-journey.md`: actual compatibility behavior and test evidence.
- This report. No final-review checkbox changed.

## Browser acceptance iteration

The first whole Django browser run (`PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test --config playwright.django.config.ts`, `/tmp/hcmusec-final-journeys.log`) passed **9/10**, including the new migrated-quote journey. The existing duplicate-resubmission test timed out after its helper advanced only one stage from a server-error details view and then waited for a Submit button while still on roster. The trace confirmed valid preserved roster fields. The test now explicitly selects **3. Review registration** before retry; no application behavior changed for this test repair. On main, `PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test --config playwright.django.config.ts --grep 'duplicate player|migrated payment quote'` passed **2/2**, 44.3s; `/tmp/hcmusec-main-journeys.log`. This covers the repaired failure and the new migration flow without repeating the other eight passing cases.

## Main continuation verification

- `pnpm check`: 0 errors/0 warnings; `/tmp/hcmusec-main-web-check.log`.
- `.venv/bin/ruff check .` from `server/`: all checks passed; `/tmp/hcmusec-main-ruff.log`.
- Read-only disposable cleanup: `/tmp/hcmusec-main-cleanup.log` records no remaining `test_registration_journey_*` databases, no fixture file, and no temporary media directories. No normal database mutation was used.
- CodeGraph was unavailable in the original temporary checkout; it was available on main and used before locating the availability code.

- `PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test`: **3/3 passed**, 27.0s; `/tmp/hcmusec-main-public-playwright.log`.
- `PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA pnpm build`: passed; `/tmp/hcmusec-main-build.log`. Existing adapter target/plugin timing notices remain.

- `pnpm exec eslint src/lib/components/registrations/RegistrationWizard.svelte src/lib/registrations/submission.ts src/routes/registration-stages.svelte.spec.ts e2e/django/registration.spec.ts`: passed; `/tmp/hcmusec-main-eslint.log`.
- `pnpm exec prettier --check src/lib/components/registrations/RegistrationWizard.svelte src/lib/registrations/submission.ts src/routes/registration-stages.svelte.spec.ts e2e/django/registration.spec.ts messages/en.json messages/vi.json ../docs/payments/payment-references.md ../docs/testing/registration-journey.md ../.superpowers/sdd/2026-09-15-staged-registration-vietqr/final-fix-report.md`: final check log `/tmp/hcmusec-main-prettier.log`. The report itself required Markdown formatting; no production source changed during final packaging.
- `git diff --check`: clean.

Final self-review found no unresolved issue within the authorized scope. Conservative legacy-token retention and legitimate paid-intake blocking while receiving settings are absent are intentional, documented outcomes. No merge, push, production deployment, bank setup, normal-database migration/seed, or final-review approval was performed by this implementer.
