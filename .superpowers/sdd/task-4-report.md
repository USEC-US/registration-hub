# Task 4 Report: Backend Turnstile Verification and Production Checks

## Status

Completed and committed as `4dcf434 feat: verify turnstile on public actions`.

## What I Implemented

- Added `TURNSTILE_SECRET_KEY` and `TURNSTILE_SITEVERIFY_URL` settings and documented both in `server/.env.example` without adding a real secret.
- Added `config.turnstile` with the `TurnstileVerificationResult` result type, stdlib `urllib` Siteverify POST, debug-only missing-secret bypass, production missing-secret rejection, request IP forwarding, failure-code propagation, and action validation.
- Added a reusable DRF `require_turnstile()` guard and applied it to registration, token obtain, registration submission, and payment-attempt submission. Token refresh remains unprotected.
- Added write-only `turnstile_token` fields to account registration and both strict registration serializers. The account serializer and payment-attempt view remove the field before persistence/service invocation.
- Added and registered `ConfigConfig`, so Django discovers `config.checks` during normal startup. The `config.E001` check rejects an absent Turnstile secret when `DEBUG=False`.
- Added service, system-check, endpoint rejection, debug-bypass, and strict-serializer acceptance coverage.

## TDD Evidence

### RED

1. Command: `uv run python manage.py test config.tests.test_turnstile -v 2`
   Result: failed with `ModuleNotFoundError: No module named 'config.turnstile'`.
   Expected because the service module did not exist.

2. Command: `uv run python manage.py test config.tests.test_settings -v 2 --keepdb`
   Result: failed with `ModuleNotFoundError: No module named 'config.checks'`.
   Expected because the system-check module did not exist.

3. Command: `uv run python manage.py test accounts.tests.test_api registrations.tests.test_api -v 2 --keepdb`
   Result: four failures: registration submission, payment attempt, account registration, and token obtain returned `201/200` instead of `400`.
   Expected because no endpoint invoked Turnstile verification yet.

### GREEN

- `uv run python manage.py test config.tests.test_turnstile -v 2 --keepdb`: 5 tests passed.
- `uv run python manage.py test config.tests.test_settings -v 2 --keepdb`: 6 tests passed.
- Final focused suite:
  `uv run python manage.py test config.tests.test_settings config.tests.test_turnstile accounts.tests.test_api registrations.tests.test_api -v 2 --keepdb`
  Result: 35 tests passed, `OK`.

## Production-Check Evidence

- Development: `DEBUG=true`, no Turnstile secret, `uv run python manage.py check` reported `System check identified no issues`.
- Production negative case: `DEBUG=false`, Turnstile secret removed, `uv run python manage.py check` exited 1 with `config.E001: TURNSTILE_SECRET_KEY must be set when DEBUG=False.`

## Other Verification

- `uv run ruff check .`: `All checks passed!`
- `git diff --check`: no whitespace errors before commit.
- The test database already existed, so focused Django suites used `--keepdb` as required.

## Files Changed

- `server/.env.example`
- `server/accounts/serializers.py`
- `server/accounts/tests/test_api.py`
- `server/accounts/urls.py`
- `server/accounts/views.py`
- `server/config/apps.py`
- `server/config/checks.py`
- `server/config/settings.py`
- `server/config/tests/test_settings.py`
- `server/config/tests/test_turnstile.py`
- `server/config/turnstile.py`
- `server/registrations/serializers.py`
- `server/registrations/tests/test_api.py`
- `server/registrations/views.py`

## Self-Review

- Confirmed each required POST action uses its specified action name and returns DRF field errors under `turnstile_token` when verification fails.
- Confirmed Siteverify uses only stdlib `urllib`, secrets remain server-only, and Cloudflare's `timeout-or-duplicate` response is preserved for clients.
- Confirmed strict serializers accept the token and that payment submission removes it before calling the service.
- Confirmed `/api/auth/token/refresh/` remains on `TokenRefreshView` with no Turnstile guard.

## Concerns

- No task-specific concerns. The broad Django suite was not run because of the pre-existing deferred `SeedDevDataCommandTests` failure described in the task context.
- The example Docker hostname is `db`; host-run verification used `DB_HOST=localhost` because Docker publishes PostgreSQL on `localhost:5432` outside its internal network.

## Review Fix: DEBUG Missing-Secret Warning

### RED

- Focused warning assertion against the committed pre-fix `server/config/turnstile.py` failed with: `AssertionError: no logs of level WARNING or higher triggered on config.turnstile`.

### GREEN

- `uv run python manage.py test config.tests.test_turnstile -v 2 --keepdb`: 6 tests passed, including `test_debug_without_secret_emits_developer_warning`.
- `uv run ruff check .`: `All checks passed!`

### Files Changed

- `server/config/turnstile.py`
- `server/config/tests/test_turnstile.py`
- `.superpowers/sdd/task-4-report.md`

The DEBUG-only missing-secret path now logs one clear developer warning per process before allowing the local bypass. The focused test resets the module guard, captures the warning deterministically, and verifies that it identifies both the missing secret and local-development bypass.
