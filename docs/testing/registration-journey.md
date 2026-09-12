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

## Main roster and substitutes

Tournament divisions configure `main_roster_size` (at least one required main player) and `substitute_limit` (zero or more optional substitutes). The public API and registration summary expose these fields. The form shows separate main and substitute sections; submitted members store `roster_role` as `main` or `substitute`.

The captain is the team representative, independently of roster role. New submissions are saved with that player in display slot 1, including when a manager selects a substitute. Captain submitters remain linked to their own slot 1; managers remain outside the player roster. These registration roles impose no match-lineup restrictions. Duplicate-player validation includes both main and substitute entries.

Apply the migrations with `server/.venv/bin/python server/manage.py migrate`. Existing configuration converts the old minimum into the required main count and the difference between maximum and minimum into substitute places. For legacy submissions, slots beyond that main count are labeled substitutes; their original captain, order, and player/institution snapshots are preserved. New member roles are stored explicitly and remain unchanged when division settings later change.

The migration test checks forward and reverse limit conversion and preservation of submitted snapshots. API tests cover a substitute representative, owner linkage, invalid role counts, and duplicate claims across main/substitute roles. The real Django browser suite covers a manager registering two main players and a substitute representative, then reviewing the submitted entry in admin.

## Player identity and student eligibility

Each main player and substitute supplies first name, last name, date of birth, Student ID, and the existing game identifier/institution choice. Names and a valid date of birth are required for every new submission; future birth dates are rejected. Student IDs remain strings so leading zeroes survive.

Enable **Students only** in the tournament admin to require Student IDs for all players in every division of that tournament. Other tournaments accept an empty Student ID. This setting collects the information needed for manual organizer review; it does not independently prove enrollment or automatically approve eligibility. Existing tournaments default to this setting being off.

The four identity fields are stored on `RegistrationMember` as snapshots, separately from account/profile data. Organizer admin shows them alongside the roster and supports searching by player name, Student ID, and institution. They are omitted from registration receipts and read serializers. Existing player snapshots, captain ordering, role assignments, contacts, and institution catalogue behavior remain intact.

The additive migrations leave unknown historical names/Student IDs blank and birth dates null. They never infer player names from gamer tags or account profiles. Backend tests cover conditional requirements, malformed/future dates, leading zeroes, guest privacy, rollback, and historical migration. Browser tests cover both policy settings and retaining identity values after institution selection; the real Django suite submits student-only entries and checks their identity details in organizer admin.

Verification after adding player identity: 154 Django tests, 209 Vitest tests, and seven real Django browser journeys passed. Svelte, lint, migration consistency, Django system checks, and the production build passed. The build used a Turnstile test site key; environment files were unchanged. Both new migrations have been applied to the local development database.
