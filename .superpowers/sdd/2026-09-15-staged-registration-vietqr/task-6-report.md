# Task 6 implementation report

Status: DONE, pending scoped and whole-branch review. Base: `21058d1`.

## Implemented

- Nine real Django/PostgreSQL browser journeys: free captain, manager with substitute captain and private identity snapshots, solo/date picker, paid guest returning through saved access in a new tab, pending proof, staff reasoned rejection/replacement, private media protection, verification followed separately by eligibility approval, signed-in account/payment navigation, lost submission response recovery, expired-entry editable retry, and duplicate rejection/resubmission. Counts describe nine tests with several related assertions per journey.
- Lost response uses `route.fetch()` to persist through the real submission endpoint, then `route.abort('failed')`. The browser recovers with its saved credential; assertions prove one submission request, one saved entry, and the same ID through the real resume endpoint. All other application requests are unmocked.
- Disposable server fixture installs clearly marked fictional receiving settings and submits an expired fixture through the actual API before adjusting only that disposable row's deadline. Mode-0600 `/tmp/hcmusec-registration-journey-fixture.json` carries its synthetic credential to Playwright and is removed in server teardown. No production test endpoint or browser clock change.
- Development seeding uses fictional snapshots only while building command-owned fixtures inside a transaction, locking the existing singleton first. It restores every operator field, enabled state and hold; an initially absent singleton is removed before commit. Error rollback preserves settings. Tests cover enabled/disabled reruns, absent settings and failure rollback in addition to existing fixtures.
- Auth SSR tests now explicitly supply `$app/state.page.url`, retaining real `svelte/server.render` assertions on POST forms and hydration-disabled submit buttons. No auth production code changed.
- Updated deployment activation, reservation recovery/rollback, proof/privacy and rate-limit docs; staged/QR TODO acceptance marked complete, automatic holder lookup/SePay deferred. Plan/spec stale pause/proposed labels corrected. Root authorized inclusion of Tasks 1–5 tracking and first four Task 6 steps; final review checkbox remains pending.

## TDD evidence

RED before receiving fixture adaptation:

```sh
# web/
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test --config playwright.django.config.ts --grep 'paid guest returns'
```

`/tmp/hcmusec-task6-journeys-red.log`: 1 failed; timed out waiting for Facebook input because paid intake was unavailable without receiving settings. The updated journey was written before adapting the Django fixture.

```sh
# server/
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test registrations.tests.test_seed_dev_data_command --keepdb --noinput
```

`/tmp/hcmusec-task6-seed-preservation-red.log`: 9 tests, failures=1/errors=8, including disabled/unconfigured destination failures and fictional-snapshot preservation expectation. Earlier baseline seed-only invocation is `/tmp/hcmusec-task6-seed-red.log`.

GREEN seed: equivalent command from workspace root (`TURNSTILE_SECRET_KEY=test-only-key server/.venv/bin/python server/manage.py test registrations.tests.test_seed_dev_data_command --keepdb --noinput`) passed 9 tests in 13.065s; `/tmp/hcmusec-task6-seed-green.log`. A subsequent failure-rollback regression is covered by the final full 248-test pass below (10 seed-command tests total).

Auth SSR RED already reproduced in `/tmp/hcmusec-baseline-auth.log` before this task: 2 failures/3 passes due to absent SvelteKit context. Final Vitest passes all five auth SSR tests with real render assertions unchanged.

First complete browser iteration: `/tmp/hcmusec-task6-journeys-first-green.log`, 5 passed/4 failed. Failures were test adaptation errors: removed confirmation data selector, expected old upload status 201 versus private-session 200, account detail now links to the dedicated payment page, and two accessible recovery controls requiring a form-scoped selector. Fixed test expectations only. No application implementation changes were needed. Final complete journey command passes 9/9, below.

Two editing shell invocations initially used a workspace-relative path while cwd was `server/` or `web/`, producing FileNotFoundError before edits. Corrected immediately; no source mutation from those failed scripts. These are execution diagnostics, not product failures.

## Final verification

Commands below ran sequentially within the frontend (no check/Vitest/build generated-artifact races). Tests/sockets/PostgreSQL and pnpm cache access used sandbox escalation as needed.

| Working directory | Exact command | Result / log |
| --- | --- | --- |
| server | `TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test --keepdb --noinput` | 248 passed, 79.442s; `/tmp/hcmusec-task6-django.log` |
| server | `TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py makemigrations --check --dry-run` | No changes detected; `/tmp/hcmusec-task6-migrations.log` |
| server | `TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py check` | No issues; `/tmp/hcmusec-task6-system-check.log` |
| server | `.venv/bin/ruff check .` | All checks passed; `/tmp/hcmusec-task6-ruff.log` |
| web | `pnpm check` | 0 errors/0 warnings; `/tmp/hcmusec-task6-web-check.log` |
| web | `PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run` | 292 passed/40 files, 35.16s; `/tmp/hcmusec-task6-vitest.log` |
| web | `PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test` | 3 passed, 25.4s; `/tmp/hcmusec-task6-playwright-green.log` |
| web | `PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test --config playwright.django.config.ts` | 9 passed, 55.8s; `/tmp/hcmusec-task6-journeys-second.log` |
| web | `PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA pnpm build` | Passed, usual adapter-auto target notice; `/tmp/hcmusec-task6-build.log` |
| web | `pnpm exec eslint e2e/django/registration.spec.ts src/routes/auth-pages.test.ts` | Passed; `/tmp/hcmusec-task6-eslint.log` |
| web | `pnpm exec prettier --check e2e/django/registration.spec.ts src/routes/auth-pages.test.ts` | Passed; `/tmp/hcmusec-task6-prettier.log` |
| workspace | `git diff --check` | Passed |

After behavior verification, repository Ruff/Prettier formatted only changed test/fixture files. No behavioral changes followed the final full-suite passes. Tests were not unnecessarily rerun after formatting.

Initial sandboxed `pnpm check` reported `unable to open database file`; escalated package-cache access resolved it. Default Playwright without `PUBLIC_TURNSTILE_SITE_KEY` stopped before tests because its configured webServer builds production (`/tmp/hcmusec-task6-playwright.log`). The test-only prefix resolves that prerequisite without changing environment files. Both `server/.env` and `web/.env` compare byte-for-byte equal to their copied original-workspace counterparts.

## Cleanup and environment evidence

The read-only final query through Django used `SELECT datname FROM pg_database WHERE datname LIKE %s` with `test_registration_journey_%`, plus `/tmp` fixture-directory/file checks. `/tmp/hcmusec-task6-cleanup-final.log` records:

```text
Disposable journey databases: []
Disposable journey media: []
Credential fixture exists: False
```

Initial cleanup inspection found one unrelated old disposable database, `test_registration_journey_8552004805b1`. It had zero active clients, only the expected `registration-journey-test` tournament and reserved fixture accounts; its sole registration dated `2026-09-12 16:06:23+00:00`, before Task 6. This distinguishes it from the current Sept 15 runs. The exact historical shutdown cause is unknown; current normal-shutdown runs left no databases/media. Narrow `DROP DATABASE test_registration_journey_8552004805b1` removed only that proven inactive harness fixture, after checking activity again. Evidence: `/tmp/hcmusec-task6-orphan-inspection.log`, `/tmp/hcmusec-task6-orphan-cleanup.log`. Ordinary configured database and the Django `--keepdb` test database were preserved. No ordinary-database migrations or seeding occurred.

No browser/dependency installation was needed beyond the already installed Chromium in `/tmp/hcmusec-playwright`. CodeGraph CLI was attempted first and unavailable in this worktree; targeted source inspection followed as authorized.

## Self-review and limitations

- Reviewed scoped diff for fixture isolation, singleton transaction/lock preservation, real API behavior, retained privacy assertions, recovery credential storage, backend-controlled expiry, and documentation consistency. No substantive application defect found in these journeys. Broader privacy/race/legacy review belongs to the pending final whole-branch review and prior Tasks 1–5 regression evidence.
- Sequential normal-config Vitest still prints the baseline `wrapDynamicImport` generated-hook diagnostic while every test passes. It is not caused by concurrent artifact generation in this final run. Existing expected negative-request Django logs, Paraglide source-map warnings, and NO_COLOR/FORCE_COLOR warnings remain. Build emits plugin timing and adapter-auto deployment-target notices.
- Root's existing fictional-data screenshots remain available at `/tmp/hcmusec-registration-desktop.png`, `/tmp/hcmusec-registration-mobile.png`, `/tmp/hcmusec-roster-mobile.png`; root reported new forms readable without horizontal overflow. Existing shared mobile-header brand wrapping is unchanged and remains a final-review scope/UX limitation. This task did not produce additional screenshots.
- A real bank-app scan, authorized bank/destination verification, and deployed scheduler checks remain operational acceptance, not claimed complete. No real transfer, bank configuration, scheduler activation, merge, or push was performed.
- Earlier deferred minor review notes (QR test substring assertion, receipt prefetch/N+1, negative-request logging, and mobile header) are preserved in `progress.md` for root's whole-branch review; none was silently treated as resolved.

## Files and commit scope

`server/e2e/serve.py`; `server/registrations/dev_seed.py`; `server/registrations/tests/test_seed_dev_data_command.py`; `web/e2e/django/registration.spec.ts`; `web/src/routes/auth-pages.test.ts`; `docs/testing/registration-journey.md`; `docs/payments/payment-references.md`; `docs/deployment/payment-images.md`; `docs/deployment/security-rate-limits.md`; new `docs/deployment/payment-reservations.md`; `docs/TODO.md`; plan/spec status and approved checkbox tracking; this report.

Implementation commit subject: `test: verify staged registration journeys and document payment operations`. Commit SHA is supplied in the implementer completion response so the report does not require a self-referential commit update.
