# Competition lifecycle: operation and release proof

Withdrawal, disqualification, restoration, exceptional ending and reopening apply
across single/double elimination, round robin, fixed Swiss and threshold Swiss.
They operate on saved competition identities and rules, independently of payment
or registration administration. See the [stage guide](competition-multi-stage.md),
[Swiss guide](competition-swiss.md) and [approved design](../superpowers/specs/2026-10-26-competition-lifecycle-design.md).

## Organizer operation

1. Open the competition workspace's Entrants tab and select Withdraw or
   Disqualify. Review the signed impact preview: preserved results, automatic
   forfeits, live contests, downstream resets, retired draws/rounds and blocked
   handoffs. Enter a private reason. Explicitly confirm live forfeits and resets
   when requested; a stale preview must be generated again.
2. Prior finalized results remain earned history. Removal applies prospectively:
   unpublished previews become stale/retired, current unresolved contests can
   resolve automatically, and later Swiss rounds omit unavailable entrants.
   Saved seeds, rules, quotas, public names and Swiss limits do not change.
3. Restore from the same entrant. Restoration removes only still-authoritative
   removal effects, including automatic effects generated after the removal.
   Review restored live progress and any downstream resets before confirming.
   Independent organizer corrections are preserved and listed as conflicts;
   restoration is not a general undo of later operator decisions. Registration
   must still be eligible. It never substitutes another registration.
4. When an earned field cannot fill the locked next stage, the workspace reports
   the blocker. Do not promote a lower finisher or change quotas to bypass it.
   Finish viable contests and resolve cutoffs when normal continuation remains
   possible. Exceptional End is available only when the server proves locked
   continuation impossible. Choose Without a champion, or explicitly award a
   determinable sole eligible survivor when allowed; a Swiss stage does not
   acquire a fabricated ordinary champion.
5. Ending freezes the source's unfinished contests and retires downstream
   previews/published fixtures while preserving their records and played scores.
   Ordinary mutation commands reject an ended competition. Reopen requires
   explicit confirmation and clears only the competition ending. It does not
   restore entrants or resurrect retired fixtures. Restore eligible entrants as
   needed, then generate, review and explicitly publish a fresh replacement.

Lifecycle management requires organizer/model permissions; live/result-impacting
changes also require match-change permission. Apply rechecks permission,
competition revision, eligibility, canonical impact, strict consent and the
signed preview's one-hour lifetime. Double submission cannot apply twice.

## Public and private history

Current standings/progression use current published fixtures. Previously public
retired fixtures and their immutable score snapshots remain historical, including
Changes links and keyboard navigation. Private previews never become public
merely because they were retired. Public EN/VI labels distinguish unavailable
entrants, ended competitions, no-champion outcomes and historical results.

Organizer Changes retains actor, private reason, provenance and impact details.
Public allowlists exclude these, registration/payment/contact data and private
fixture IDs. Restoration preserves original public entrant identity. An ended
competition's public outcome is distinct from an ordinary stage champion.

## Upgrade and recovery

Migration `competitions.0006_competition_lifecycle` follows `0005_swiss`; it adds
ending/provenance/availability state and preserves legacy identities and results.
The PostgreSQL migration tests cover seeded upgrade and lifecycle backfill
invariants. Before a release, stop writes, take and verify a database backup,
record the exact code commit and migration state, and retain matching media and
environment configuration. Run migrations/checks on a restored staging copy
before opening writes with the matching application version.

If recovery is required after lifecycle writes, prefer a forward fix. Otherwise
stop writers, preserve a separate incident backup, restore the known matching
code **and database** backup (plus matching media if applicable), migrate only as
appropriate for that code, and verify entrants, published/historical fixtures,
Changes and revision consistency before reopening traffic. Reverting only code
or reversing the schema can lose provenance/availability/ending semantics; it is
not a safe operational rollback. This proof did not perform a production backup
restore or deploy anything.

## Reproduce the release checks

Use disposable PostgreSQL with UTF8/template0 and a test-only Turnstile key;
collect static assets for admin tests. Never copy live credentials. The recorded
run used PostgreSQL 18.6 on 127.0.0.1:55439, role `lifecycle`, database
`hcmusec_lifecycle`, `/tmp/hcmusec_lifecycle_settings.py`, and
`UV_CACHE_DIR=/tmp/hcmusec-lifecycle-uv-cache`. From `server/`:

```sh
export PYTHONPATH=/tmp
export DJANGO_SETTINGS_MODULE=hcmusec_lifecycle_settings
uv run python manage.py test competitions.tests.test_concurrency --noinput
uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command registrations.tests.test_services registrations.tests.test_reservation_concurrency registrations.tests.test_admin_actions --noinput
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py shell < competitions/benchmarks/swiss_publication.py
```

Race tests use independent connections and barriers. Registration-approval races
hold the first transaction until `pg_blocking_pids` proves the second connection
is waiting. Score/removal, publication/removal, duplicate restore, end/score,
end/publication and duplicate reopen assert legal resulting state, one competition
revision/event, continuous history and a matching public revision. Approval
versus restoration/publication verifies the shared division-lock boundary.
Do not substitute SQLite or accept skipped PostgreSQL races.

The benchmark creates a UUID-named local database, migrates it, persists 256
entries and 64 rounds (8,192 fixtures), and measures the actual production final
publication. Fixture setup timing excludes database creation/migrations and uses
real pairings/fingerprints/audits and internal persistence
with bulk 1–1 historical scores; it is not 8,064 end-to-end scoring commands.
Counters wrap actual SQL and the solver. Assertions require 63 completed rounds,
one current-round solver call, unchanged 8,064 historical matches and prior
ChangeSets, one new event/revision and final PUBLISHED state. Cleanup drops only
its own database, including on failure. Run without competing tests/builds.

## Recorded evidence and limits (2026-10-26)

Task 9 starts from `b22d40f549c2ef031b00075f833e962f4a6a903d` on
`feat/tournament-brackets`; its changes are tests, benchmark and documentation.
Detailed commands and full logs are in the ignored execution workspace
`.superpowers/sdd/2026-10-26-competition-lifecycle/task-9-report.md`.

Fresh Task 9 checks:

- Combined competition, seed, registration services/reservation concurrency/admin
  gate: **486 tests passed in 754.657s**, zero skips, exit 0. The final race-only
  strengthening was then verified separately: **27 tests passed in 19.148s**,
  zero skips, exit 0.
- Django check: zero issues. Migration drift: none. Scoped Ruff check/format,
  frontend ESLint and diff whitespace checks passed.
- Persisted final Swiss publication: **51.307509s**, **238 SQL executions**,
  **one solver call / 4.169810s**, ending PUBLISHED with one event/revision and
  unchanged prior matches/history. Fixture setup: **914.462635s**, excluding
  database creation/migrations. Own database
  `swiss_publication_20d42cf137d845eca3a9cdd10c7825d4` was removed, exit 0.
  No competing test/build processes ran during the measurement. The earlier
  disposable script was unavailable, so this is a new repeatable case with the
  same persisted field/round/match counts, not a controlled speed comparison.
  The observed publication duration is substantial; this proves absence of
  historical solver replay, not an acceptable production latency budget.

Unchanged product/browser source retains Task 8 evidence at `b22d40f`: both
complete bracket browser files passed **16/16 in 5.1m**; focused frontend tests
passed **42/42 across three files**; Svelte/i18n check had **0 errors/0 warnings**;
production build passed. Exact frontend commands:

```sh
pnpm --dir web exec vitest run src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts src/lib/api/competitions.test.ts
pnpm --dir web check
pnpm --dir web build
# From web/, with explicit disposable DB and test-only secrets:
pnpm exec playwright test --config=playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts
```

Browser success is behavioral assertion evidence, **not a clean-console claim**.
`task-8-browser-green-resumed.log:7244–7264` includes Vite's HMR reload warning
and `TypeError: Failed to fetch` in SvelteKit `load_data → load_route → _invalidate`
during the existing single/double-elimination spectator journeys. Neighboring
competition API requests returned HTTP 200 and both journeys passed. This locates
the symptom in client navigation/invalidation under the development server, but
the log does not prove why the fetch failed or exclude a runtime defect. No
production-server browser/console gate was run. Build warnings remain the
`@internationalized/date` dependency cycles and empty generated env/navigation
chunks; they did not fail the build.

## V1–V5 reconciliation

| Gate | Evidence and remaining boundary |
| --- | --- |
| V1 Format behavior | Full competition suite plus lifecycle tests cover five formats, earned qualifier shortfalls, prospective removal, provenance-aware restore, Swiss availability/history, ending feasibility and locked rules; existing format tests retain byes, both final policies, ties and scoring limits. |
| V2 Mutation integrity | PostgreSQL race gate, stale-token/replay/rollback tests, shared projection and played-suffix history tests; registration service/reservation/admin gates verify the shared lock boundary. |
| V3 Permissions/privacy | Lifecycle workspace/direct-command/API tests and seed/browser checks enforce permissions, strict consent, public allowlists and private reasons/provenance. This is bracket-scope proof, not a platform-wide security audit. |
| V4 Full workflow | 16 real Django/admin/Svelte journeys include removal/restore, stale confirmation, end/reopen/fresh replacement, Swiss continuation, historical links, EN/VI and 390px containment. HMR/fetch console caveat above remains; no realtime claim. |
| V5 Delivery | Synthetic rerunnable lifecycle fixtures, this operating/recovery guide, migration tests and repeatable persisted-publication measurement. Final whole-branch review found no Critical or Important issues. No production restore rehearsal, latency guarantee or deployment. |

V1–V5 are complete for the agreed bracket-core scope following independent task
reviews and final whole-branch review of `95ed9eb..b8b811d` on 2026-10-26, with
no Critical or Important findings. The review's minor stale documentation
references were corrected during final status reconciliation. Full review
evidence remains in the ignored execution workspace's `final-review.md`.

The unknown-cause development-browser fetch errors remain an accepted,
nonblocking verification limitation, not proof of harmlessness. The measured
51.308-second publication remains an operational consideration; no production
latency budget has been accepted. Realtime, providers, TFT, production readiness
and platform-wide permission/privacy hardening retain their separate project
scope. The branch was kept in place without merge, push or deployment.
