# Registration journey verification

Run from `web/` with the Python and Node dependencies already installed:

```sh
pnpm exec playwright install chromium
pnpm exec playwright test --config playwright.django.config.ts
```

The suite starts Django on `127.0.0.1:8015` and Svelte on `127.0.0.1:4175`. Both ports must be available. It uses the PostgreSQL connection credentials from `server/.env`; that database user must be able to create and drop test databases. Each run creates a uniquely named `test_registration_journey_*` database, migrates and seeds it, and removes it on normal shutdown. Uploaded files live in a temporary directory. The configured development database is never flushed or seeded by this harness.

The test fixture accounts use reserved `.test` email addresses and a fixed test password, and exist only in that disposable database. The organizer fixture has the actual `Organizers` permissions rather than superuser access.

Application API requests are real: the suite does not intercept registration, catalogue, account, payment, or admin responses. It uses the existing development Turnstile bypass so it can run unattended; backend tests separately cover challenge rejection and side effects. It does not verify the live Cloudflare challenge service.

The browser journeys cover guest captain and manager teams, solo registration, signed-in registration and later proof upload, initial paid guest proof and private downloads, organizer payment verification and registration approval, duplicate rejection, and organizer rejection followed by corrected resubmission. A JavaScript-disabled browser also verifies that credential forms use POST and keep submission disabled before hydration. Backend tests additionally cover concurrency, snapshot preservation after institution rename, required contacts, invalid proof, and rollback cleanup.

Run backend verification from `server/`:

```sh
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test --keepdb
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py makemigrations --check --dry-run
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py check
```

The placeholder key satisfies the Django test runner's configuration check. Tests override the challenge settings or mock verification as appropriate; it is not a production credential.

Player duplicate detection uses the normalized submitted game identifier and institution within a division. This is a claim check, not verified game-account ownership. Riot ID variants and Steam profile URLs/IDs are not resolved to a shared platform identity.

## Verified on 2026-09-12

- Django: 136 tests passed, including concurrent duplicate submission against PostgreSQL.
- Vitest: 206 tests passed across 32 files.
- Real Django/PostgreSQL Playwright suite: seven tests passed.
- Existing mocked public-navigation Playwright suite: three tests passed.
- Production build, Svelte checks, changed-file ESLint/Prettier, Ruff, migration consistency, and Django system checks passed.
- Disposable browser-test databases were confirmed removed after shutdown.

The full Vitest run emits a `wrapDynamicImport` diagnostic from Vitest's browser import transform reaching SvelteKit's Node test-server middleware. It predates the new auth SSR tests; all test assertions pass. The real Django browser suite and production build also pass. This test-tooling diagnostic is not counted as a failed application journey.
