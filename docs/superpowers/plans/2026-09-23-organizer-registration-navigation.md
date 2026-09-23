# Organizer Registration Navigation Implementation Plan

**Goal:** Continue the organizer roadmap with counts and direct review navigation.
**Architecture:** Extend the existing tournament admin classes with annotated
querysets, count links, and read-only detail fields. Reuse registration changelists.
**Tech Stack:** Django ORM/admin and existing Django TestCase coverage.

## Execution

- [x] Extend `server/tournaments/tests/test_admin.py` with real admin requests for
  totals, filtered destinations, detail pages, empty records, and permission gates.
  Include a query assertion that rendering annotated summaries does not query.
- [x] Run the focused tests and confirm missing-count failures.
- [x] Extend `server/tournaments/admin.py` using `Count(..., distinct=True)`,
  `reverse(..., query=...)`, `format_html`, and native read-only fields.
- [x] Run `python manage.py test tournaments.tests.test_admin
  tournaments.tests.test_admin_permissions registrations.tests.test_admin_actions
  --noinput`, Django checks, and Ruff. If PostgreSQL is unavailable, run this
  bounded admin suite with an in-process in-memory SQLite database and explicitly
  retain PostgreSQL verification as outstanding.
- [x] Update `docs/TODO.md` with current state, completed scope, and verification
  limits. Leave broader organizer work open. Commit authorized by the user after
  reviewing the completed slice.

## Verification — 2026-09-23

- Baseline: four existing tournament admin tests passed on in-memory SQLite.
  The new count/link tests then failed on missing count methods, as expected.
- Final: all 12 tests in the three admin modules above pass on PostgreSQL 18,
  including an unrelated tournament entry to prove filtering excludes it.
  The test database was removed by Django after the run.
- PostgreSQL test-process overrides matched local `compose.yaml`: host
  `127.0.0.1`, port `5432`, database `usec_tnmt_registration`, and the Compose
  development credentials. `TURNSTILE_SECRET_KEY=test-only-key` was used for
  checks/tests; no environment files or live application data were changed.
- `python manage.py check`, `ruff check server`, and changed-file
  `ruff format --check` pass. Admin requests emit the existing warning that
  local `server/staticfiles/` has not been collected; tests use normal static
  storage and exercise real rendered pages.
- Frontend `pnpm run check` passes with zero errors/warnings after restoring
  locked dependencies and running `pnpm exec paraglide-js compile --project
  ./project.inlang --outdir ./src/lib/paraglide --strategy url` from `web/`.
- Independent code review found no blocking issues; its missing cross-tournament
  fixture finding was addressed before the final PostgreSQL run.
- Full application regression, browser visual review, deployment activation, and
  production acceptance were outside this navigation slice.
