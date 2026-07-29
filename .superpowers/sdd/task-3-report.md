# Phase 1 Task 3 Report

## Status

DONE_WITH_CONCERNS

## Commit

- `ec6e97a feat: use institutions in account settings`

## Delivered

- Added the typed `/institutions/` search client and reusable `InstitutionCombobox`.
- The combobox supports debounced server search, result selection, custom-label fallback, ArrowUp/ArrowDown/Enter/Escape behavior, and account field errors.
- Registration and profile now submit `institution_id` or `institution_label`; account responses and all affected frontend fixtures use `CurrentUser.institution`.
- Registration roster snapshots remain independent of account data and initialize empty.
- Updated English and Vietnamese account/institution copy.
- Updated account test factory staff fixtures to provide the required private student ID.

## TDD Record

- RED: `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts` failed because `InstitutionCombobox.svelte` did not exist.
- RED: account/registration suite failed against the absent institution client/component.
- GREEN: the focused combobox suite now covers catalogue selection, custom labels, keyboard selection, and errors.
- A post-implementation browser-test locale leak was diagnosed from rendered Vietnamese labels; the spec now resets Paraglide locale in `beforeEach` and `afterEach`.

## Verification

- `pnpm exec paraglide-js compile --project ./project.inlang --outdir ./src/lib/paraglide`: PASS.
- `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts`: PASS, 4 tests.
- `pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts`: PASS, 33 tests.
- `pnpm check`: PASS, 0 errors and 0 warnings.
- `uv run ruff check .`: PASS, `All checks passed!`.
- Svelte MCP autofixer: register and profile pages reported no issues; the combobox initially reported a captured `initialLabel`, which was corrected with mount-time initialization; final combobox autofixer result had 0 issues and 0 suggestions.
- `uv run python manage.py test accounts config registrations tournaments -v 2 --keepdb`: account, config, registration, and tournament tests pass apart from the deferred seed failures below.

## Concern

The broad Django command finishes with six deferred development-seed errors because `server/registrations/dev_seed.py` still sends removed `User.school` values to `update_or_create`. This task intentionally did not expand into the separately deferred seed feature.

- `registrations.tests.test_seed_dev_data_command.SeedDevDataCommandTests.test_command_requires_explicit_non_debug_override`
- `registrations.tests.test_seed_dev_data_command.SeedDevDataCommandTests.test_command_creates_documented_accounts_and_permissions`
- `registrations.tests.test_seed_dev_data_command.SeedDevDataCommandTests.test_command_seeds_public_availability_and_hides_draft`
- `registrations.tests.test_seed_dev_data_command.SeedDevDataCommandTests.test_command_seeds_registration_status_payment_and_timeline_matrix`
- `registrations.tests.test_seed_dev_data_command.SeedDevDataCommandTests.test_rerun_restores_seed_owned_data_and_preserves_unrelated_records`
- `registrations.tests.test_seed_dev_data_command.SeedDevDataCommandTests.test_seed_failure_rolls_back_bootstrap_accounts_and_catalog`

The pre-existing `.superpowers/sdd/progress.md` modification was left uncommitted and untouched.

## Review Fix: Prevent Stale Institution Selection

### What Changed

- `InstitutionCombobox` now synchronously invalidates in-flight searches, clears rendered results and the active index, and marks non-empty input as loading before the 200 ms debounce begins.
- The custom-label fallback is therefore withheld until the matching search completes with no catalogue results.
- Added regressions for removing the stale click target and preventing immediate Enter from selecting a stale active result. A literal stale-option click cannot occur after the fixed synchronous removal; the click regression asserts that the option is no longer mounted before such a click is possible.

### TDD RED/GREEN Evidence

- RED: `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts` failed with the stale option still in the document and Enter selecting `{ institution_id: 7 }`.
- GREEN: the same focused suite passed with 6 tests after the state-reset change.

### Svelte Autofixer

- Official Svelte MCP `svelte_autofixer` on `InstitutionCombobox.svelte`: 0 issues, 0 suggestions, no further tool call required.

### Exact Commands and Results

- `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts`: PASS, 1 file and 6 tests.
- `pnpm check`: PASS, `svelte-check found 0 errors and 0 warnings`.
- `git diff --check`: PASS, no whitespace errors.

### Files Changed

- `.superpowers/sdd/task-3-report.md`
- `web/src/lib/components/forms/InstitutionCombobox.svelte`
- `web/src/lib/components/forms/institution-combobox.svelte.spec.ts`

## Review Fix: Cancel Institution Search on Escape

### What Changed

- Escape now clears a pending debounce timer, invalidates the current request generation, clears results and the active index, and ends the loading state.
- Added an in-flight-search regression: resolving a request after Escape cannot remount its catalogue option.

### TDD RED/GREEN Evidence

- RED: `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts` failed with `University of Science` still mounted after Escape when the controlled request resolved.
- GREEN: the same command passed after request invalidation and debounce cancellation were added.

### Svelte Autofixer

- Official Svelte MCP `svelte_autofixer` on `InstitutionCombobox.svelte`: 0 issues, 0 suggestions, no additional tool call required.

### Exact Commands and Results

- `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts`: RED: 1 failed, 6 passed; GREEN: PASS, 1 file and 7 tests.
- `pnpm check`: PASS, `svelte-check found 0 errors and 0 warnings`.

### Files Changed

- `.superpowers/sdd/task-3-report.md`
- `web/src/lib/components/forms/InstitutionCombobox.svelte`
- `web/src/lib/components/forms/institution-combobox.svelte.spec.ts`
