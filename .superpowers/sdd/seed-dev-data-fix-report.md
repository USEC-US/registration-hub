# Seed Development Data Institution Fix

## Root Cause

`accounts` migration `0003_institution_catalogue` removed `User.school` and
introduced the nullable `User.institution` relationship. The development seed
module still supplied `school` to `User.objects.update_or_create()` and listed
it in `save(update_fields=...)`, so every `seed_dev_data` invocation raised
`FieldError: Invalid field name(s) for model User: 'school'`.

## Files Changed

- `server/registrations/dev_seed.py`
  - Creates or reuses the HCMUS catalogue institution (`value="222"`).
  - Assigns it to the seeded player and clears institutions for organizer and
    admin accounts.
  - Replaces all obsolete `school` writes with `institution` writes.
- `server/registrations/tests/test_seed_dev_data_command.py`
  - Asserts the seeded player institution, null organizer/admin institutions,
    rerun restoration, catalogue idempotence, and rollback of the seeded
    institution.

## Commands Run

All Django commands used `DEBUG=true`, `SECRET_KEY=local-dev-secret`,
`TURNSTILE_SECRET_KEY=test-turnstile-secret`, and the local Postgres database
at `localhost/usec_tnmt_registration` as `postgres`.

1. `uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2 --keepdb`
   - First run with the obsolete `POSTGRES_*` variable names stopped during test
     database setup because this project reads `DB_*` settings.
   - Re-run with the project-standard `DB_*` settings: 6 tests discovered,
     6 expected `FieldError` errors, reproducing the stale `school` failure.
2. `uv run python manage.py test registrations.tests.test_seed_dev_data_command -v 2 --keepdb`
   - 6 tests run, all passed.
3. `uv run python manage.py test -v 2 --keepdb`
   - 91 tests run, all passed.
4. `uv run ruff check .`
   - All checks passed.

## Commit

- `f5900a9` `fix: seed development institution`
