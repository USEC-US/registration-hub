# Registration journey verification

Run from `web/` with the Python and Node dependencies already installed:

```sh
pnpm exec playwright install chromium
pnpm exec playwright test --config playwright.django.config.ts
```

The suite starts Django on `127.0.0.1:8015` and Svelte on `127.0.0.1:4175`. Both ports must be available. It uses the PostgreSQL connection credentials from `server/.env`; that database user must be able to create and drop test databases. Each run creates a uniquely named `test_registration_journey_*` database, migrates and seeds it, and removes it on normal shutdown. Uploaded files live in a temporary directory. The configured development database is never flushed or seeded by this harness.

The test fixture accounts use reserved `.test` email addresses and a fixed test password, and exist only in that disposable database. The organizer fixture has the actual `Organizers` permissions rather than superuser access.

Application API requests are real. The lost-response tests forward an actual registration submission to Django, then drop the browser response and recover the same committed ID using the saved credential; it does not stub persistence or API payloads. It uses the existing development Turnstile bypass so it can run unattended; backend tests separately cover challenge rejection and side effects. It does not verify the live Cloudflare challenge service.

The ten browser journeys cover free guest captain and manager teams with a substitute representative, solo registration, signed-in payment via the account page, paid guest return in a new tab, pending proof, staff rejection and replacement, private proof downloads, separate payment verification and eligibility approval, lost-response recovery, expired-entry retry, and duplicate rejection followed by organizer rejection and resubmission. A JavaScript-disabled browser also verifies that credential forms use POST and keep submission disabled before hydration. Backend tests additionally cover concurrency, snapshot preservation after institution rename, required contacts, invalid proof, and rollback cleanup.

Run backend verification from `server/`:

```sh
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test --keepdb
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py makemigrations --check --dry-run
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py check
```

The placeholder key satisfies the Django test runner's configuration check. Tests override the challenge settings or mock verification as appropriate; it is not a production credential.

Player duplicate detection uses the normalized submitted game identifier and institution within a division. This is a claim check, not verified game-account ownership. Riot ID variants and Steam profile URLs/IDs are not resolved to a shared platform identity.

## Staged payment acceptance (2026-09-15)

The disposable database contains a clearly labeled fictional receiving destination. Never send money to it. An expired fixture is created through the real submission API, then only its database deadline is moved into the past. Its random credential is transferred through a temporary file created atomically with mode 0600 and exclusive/no-follow flags, rejecting existing files and symlinks. Shutdown removes only the fixture created by that run. No production endpoint or browser clock manipulation advances Django time.

Required commands, from `server/`:

```sh
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test --keepdb --noinput
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py makemigrations --check --dry-run
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py check
.venv/bin/ruff check .
```

From `web/`, run sequentially because these tools share generated SvelteKit/Paraglide artifacts:

```sh
pnpm check
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run
PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test --config playwright.django.config.ts
PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA pnpm build
```

The browser-cache prefix above is the implementation environment's installed Chromium location; omit it when using a normal Playwright installation. The default Playwright suite builds the application and therefore also requires the test-only Turnstile key. Environment files remain unchanged. Missing browsers, restricted local sockets, or package-cache permissions are environment prerequisites, not product test failures.

Task 6 verification: 248 Django tests, 292 Vitest tests across 40 files, nine real Django browser journeys, and three public-navigation Playwright tests passed. Production build, Svelte checks, migration consistency, Django system checks, Ruff, and changed-file ESLint/Prettier pass. The two baseline auth SSR failures were repaired by supplying SvelteKit page context in the test, preserving assertions on real SSR output. Development seed regressions verify existing configured/disabled bank settings and hold duration survive reruns and failed seeding. Full results and exact logs are in the Task 6 implementation report.

Sequential Vitest still emits the known `wrapDynamicImport` diagnostic from generated SvelteKit hooks, while all assertions pass. Real Django journeys emit existing Paraglide sourcemap and terminal-color warnings. These diagnostics are distinguished from application acceptance. A real banking-app scan, authorized destination verification, and deployed expiry scheduler checks remain operational acceptance steps; no real transfer or scheduler activation was performed.

The migration regression uses a real unattached quote and the actual registration route. It verifies organizer guidance and the explicit unpaid boundary, submits without the old token or proof, drops a real committed response, and confirms same-instance recovery clears only the browser token while the original server quote remains readable. Route component tests additionally cover validation failure, refresh/division isolation, a missing-entry replay after reload (including a lost replay response), read-only recovery with conservative old-token retention, unrelated saved entries, and a changed token at completion. Backend regressions assert one payment prefetch for four paid account receipts (including effective expiry), fresh state through upload/rejection/replacement/verification, and restrictive fixture permissions at creation with preexisting symlink rejection.

Consolidated fix verification: the full Django regression passed 253 tests and the full Vitest regression passed 300 tests across 40 files before the later availability-message edit. On the final main tree, the affected route/submission suite passes 47 tests, Svelte checks report no errors or warnings, public Playwright passes 3 tests, and the production build passes. The initial real Django run passed 9 journeys; its remaining duplicate-resubmission test needed an explicit return to Review after server validation. That repaired journey and the new migrated-quote journey both pass in the scoped main rerun (2/2). The final focused commands from `web/` were:

```sh
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run src/routes/registration-stages.svelte.spec.ts src/lib/registrations/submission.test.ts
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test --config playwright.django.config.ts --grep 'duplicate player|migrated payment quote'
```

Final review completed on 2026-09-16 for implementation commit `54e3535` on main. The legacy-session guard, receipt query count, QR boundary assertion, secure fixture creation, and availability messages passed scoped re-review with no open substantive findings. Full-suite counts above precede the last availability-only UI change; the final affected paths are covered by the 47-test run and browser/build checks. Disposable journey databases, media, and credential files were confirmed removed.

Availability regressions distinguish server schedule state and capacity from payment readiness. An open paid division with unavailable payment setup shows organizer-contact guidance in English/Vietnamese; free registration, saved access, and draft restoration remain available as appropriate. No test invents a receiving bank or changes the real division dates.

## Main roster and substitutes

Tournament divisions configure `main_roster_size` (at least one required main player) and `substitute_limit` (zero or more optional substitutes). The public API and registration summary expose these fields. The form shows separate main and substitute sections; submitted members store `roster_role` as `main` or `substitute`.

The captain is the team representative, independently of roster role. New submissions are saved with that player in display slot 1, including when a manager selects a substitute. Captain submitters remain linked to their own slot 1; managers remain outside the player roster. These registration roles impose no match-lineup restrictions. Duplicate-player validation includes both main and substitute entries.

Apply the migrations with `server/.venv/bin/python server/manage.py migrate`. Existing configuration converts the old minimum into the required main count and the difference between maximum and minimum into substitute places. For legacy submissions, slots beyond that main count are labeled substitutes; their original captain, order, and player/institution snapshots are preserved. New member roles are stored explicitly and remain unchanged when division settings later change.

The migration test checks forward and reverse limit conversion and preservation of submitted snapshots. API tests cover a substitute representative, owner linkage, invalid role counts, and duplicate claims across main/substitute roles. The real Django browser suite covers a manager registering two main players and a substitute representative, then reviewing the submitted entry in admin.

## Player identity and student eligibility

Each main player and substitute supplies first name, last name, date of birth, and the existing game identifier. Names and a valid date of birth are required for every new submission; future birth dates are rejected. Student IDs remain strings so leading zeroes survive.

Enable **Students only** in the tournament admin to require Student IDs and schools for all players in every division of that tournament. Other tournaments accept an empty Student ID and school. School is also optional during account signup and profile edits. This setting collects the information needed for manual organizer review; it does not independently prove enrollment or automatically approve eligibility. Existing tournaments default to this setting being off.

The four identity fields are stored on `RegistrationMember` as snapshots, separately from account/profile data. Organizer admin shows them alongside the roster and supports searching by player name, Student ID, and institution. They are omitted from registration receipts and read serializers. Existing player snapshots, captain ordering, role assignments, contacts, and institution catalogue behavior remain intact.

The additive migrations leave unknown historical names/Student IDs blank and birth dates null. They never infer player names from gamer tags or account profiles. Backend tests cover conditional requirements, malformed/future dates, leading zeroes, guest privacy, rollback, and historical migration. Browser tests cover both policy settings and retaining identity values after institution selection; the real Django suite submits student-only entries and checks their identity details in organizer admin.

Verification after adding player identity: 154 Django tests, 209 Vitest tests, and seven real Django browser journeys passed. Svelte, lint, migration consistency, Django system checks, and the production build passed. The build used a Turnstile test site key; environment files were unchanged. That historical verification predates this staged-payment change; this implementation applied migrations only to disposable/test databases.
