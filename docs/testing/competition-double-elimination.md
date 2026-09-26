# Double-elimination competition verification

Implementation follows the [approved plan](../superpowers/plans/2026-09-27-double-elimination.md).
The focused integration checks below passed on 2026-09-27.

## Organizer operation

Use the existing competition workspace linked from a tournament division. Configure
double elimination, choose a grand-final policy, select approved registrations,
save manual or randomized seeds, review the upper/lower/finals sections, then
publish. Publication locks the format, policy, seeds, and routes. Scheduling and
valid series overrides remain available before a match starts.

| Policy | Deciding match |
| --- | --- |
| Reset | The first final decides if the upper entrant wins. A lower-entrant win activates the reserved reset final. |
| No reset | The first final always decides, including when the upper entrant receives their first loss. |

The first final places the upper winner in side 1 and the lower winner in side 2.
The reserved reset has the first-final loser in side 1 and winner in side 2. It
can be scheduled and assigned a series override while conditional, but cannot be
started or scored until required. A final marked **Not required** is not a bye or
a played result.

Upper played/forfeit losers follow their saved lower routes. A lower loss
eliminates. Structural byes have no losing entrant or invented score. Double
forfeits eliminate both entrants and send neither onward; an empty final path
finishes with **No champion**.

Correct a result through its signed impact preview and explicit confirmation.
Inspect changed participants, results to reset, and reset-final activation changes.
Only affected contests lose their current results; unchanged ordered pairings
retain them. Changes preserves old scores and cleared match lifecycle data. The
internal reason and organizer identity are restricted to authorized organizers.
Stale forms and stale correction previews require a refresh.

Public brackets use `/tournaments/<slug>/games/<division-id>/bracket` and normal
HTTP refresh. Only published draws and allowlisted public Changes are exposed.

## Development fixtures

From the repository root, against a development database:

```sh
cd server
uv run python manage.py migrate
uv run python manage.py bootstrap_organizers
uv run python manage.py seed_dev_data
```

For an intentional **non-production** database configured with `DEBUG=False`, use
`uv run python manage.py seed_dev_data --allow-non-debug`. This override is not
production-safe; the command creates predictable development accounts.

The `dev-usec-double-elimination` tournament contains a ready 16-team Valorant
reset division and a completed five-team League of Legends no-reset division. Existing sponsor, Chess, and
League of Legends fixtures remain available. The 16-team division uses BO1 by
default, with BO3 upper semifinals/final, lower final, and finals. Both the teams
and double-elimination series allocation are synthetic. All registrations are
approved, free, and contain five fictional roster members. The reset bracket has
30 regular matches and one conditional final; the five-team bracket has 14
structural matches, including automatic byes/empty paths. Reruns preserve published
bracket IDs and results while restoring fixture registration snapshots.

The supplied tournament workbook informed only field size and series variation:
its verified 16-team bracket is single elimination. No personal data is imported,
and neither tests nor seed commands require the workbook.

## Migration and rollback

Migration `competitions/0002_double_elimination` adds section, loser-source,
grand-final-policy, and conditional-final support. Single-elimination rows keep
their existing values. Legacy double-elimination stage stubs receive `RESET`
before the new policy constraint is applied; new setup requires an explicit
policy. Review any legacy unpublished stub before publishing it.

Once real double-elimination data exists, rolling back application code alone is
unsafe: older commands do not understand loser routes and conditional finals.
Prefer a forward fix, or restore a matching database/application backup. Reversing
the migration is not a safe rollback for populated brackets.

## Recorded evidence

| Check | Result |
| --- | --- |
| PostgreSQL competition + development seed suite | 89 tests passed with `--keepdb`; no skips. |
| Staged-equivalent seed module, excluding unrelated sponsor additions | 12 tests passed; full working-tree seed module also passed 13 tests. |
| Migration drift / Django system checks / focused Ruff | No changes detected; no system-check findings; clean. |
| Focused API/loader/Svelte Vitest suite | 16 tests passed after the public UI review fixes. |
| i18n guard and Svelte check | Zero errors and warnings. |
| Changed frontend Prettier / ESLint | Clean. |
| Real Django/PostgreSQL browser journeys | Four scenarios passed across initial and focused reruns: existing SE organizer/public; new DE organizer/public. |
| Production build | Passed; existing dependency circular-import and empty-chunk warnings remain. |
| Diff whitespace check | Clean. |

The new organizer journey uses a disposable four-team fixture and exercises setup,
manual seed preview, publication, upper/lower results, a lower winner activating the
reset, a played reset, and correction confirmation making it unnecessary. Public
refresh shows the corrected state and activation history, retains cleared scores
in the public Changes API, and excludes the private reason. Separate public tests
verify English/Vietnamese section headings, keyboard Tab focus, and a 390-pixel
viewport without page overflow. Initial new browser failures were test-selector
mismatches with existing accessible labels; focused reruns passed after matching
those labels. Each browser run creates and removes a unique PostgreSQL database.

Reproduce the focused checks from the relevant application directory:

```sh
# server/
TURNSTILE_SECRET_KEY=competition-test-key uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command --keepdb
TURNSTILE_SECRET_KEY=competition-test-key uv run python manage.py makemigrations --check --dry-run
TURNSTILE_SECRET_KEY=competition-test-key uv run python manage.py check
uv run ruff check competitions registrations/dev_seed.py registrations/tests/test_seed_dev_data_command.py e2e/serve.py

# web/
pnpm check
pnpm test:unit --run src/lib/api/competitions.test.ts src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts
pnpm exec playwright test --config playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts
pnpm build
```

Local verification used equivalent installed Node entrypoints because the pnpm
launcher stalled in this environment. PostgreSQL and browser processes needed local
network access; no SQLite result is used as evidence for locking behavior.

The remaining backlog includes round robin, Swiss, stage handoffs, qualification
ties, withdrawal/disqualification commands, TFT, and realtime delivery.
