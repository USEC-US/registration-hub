# Single-elimination competition verification

Verified on 2026-09-25 for the first slice in
[the approved implementation plan](../superpowers/plans/2026-09-25-competition-core-single-elimination.md).

## Delivered workflow

An organizer opens a division in Django Unfold, creates its competition, configures
the standalone single-elimination stage, selects approved registrations, saves a
manual or randomized draw, reviews it, and publishes it. Match actions cover
scheduling, round and match series-length overrides, progress, final results, and
signed correction previews with downstream resets. Generated rows and Changes are
read-only outside those guarded actions.

The public route is
`/tournaments/<slug>/games/<division-id>/bracket`. It shows only a published
draw and public Changes. The page has desktop round columns, a mobile round list,
a keyboard-focusable scroll region, and English and Vietnamese labels. Reads use
normal HTTP; viewers refresh explicitly after concurrent revisions.

`seed_dev_data` creates one repeatable five-player Chess bracket with structural
byes and a scheduled match. The disposable Playwright database creates a completed
three-player bracket, corrects a semifinal after its final was played, replays the
final, and retains the public correction event. No fixture touches the configured
development database.

## Organizer operation

Run `bootstrap_organizers` after deployment so members of the `Organizers` group
receive the competition permissions. Use the **Competition** link on a tournament
division and follow the workspace in order: setup, entrants, draw, publish, then
match actions. A stale form is rejected by its competition revision. Result
correction requires the server-generated impact preview, confirmation, and an
internal reason; the public event omits that reason and organizer identity.

## Migration and rollback

Apply `competitions/migrations/0001_initial.py` with the normal Django migration
command. The migration is additive and does not rewrite registration or tournament
rows. Back up PostgreSQL before deploying it.

Rolling the `competitions` app back to zero drops every competition, bracket,
match, and Change record. Do that only before real competition data exists. After
organizers have created brackets, keep the migration applied and roll the
application code forward, or restore the database backup if a data rollback is
required.

## Recorded evidence

The following checks ran against PostgreSQL 18 and Chromium:

| Check | Result |
| --- | --- |
| Focused Django competition, authorization, permission bootstrap, seed, admin, API, command, model, generator, and concurrency suite | 30 passed |
| `manage.py makemigrations --check --dry-run` | No changes detected |
| `manage.py check` | No issues |
| `ruff check .` | Passed |
| `pnpm check` | 0 errors and 0 warnings |
| Focused competition Vitest suite | 12 passed across 3 files |
| Default public Playwright suite | 3 passed |
| Real Django/Svelte Playwright suite | 11 passed, including the bracket journey |
| Production SvelteKit build | Passed |
| Prettier and ESLint on every changed frontend file | Passed |

The real bracket journey starts disposable Django and Svelte servers, navigates
from the public tournament page, reads the corrected result without the private
reason, focuses the bracket scroller, switches to Vietnamese, verifies the mobile
presentation, and checks that the page does not overflow a 390-pixel viewport.
The complete real Django browser suite also preserves all ten existing registration
journeys.

Three repository-wide baselines remain outside this slice:

- The 273-test Django run passed 268 tests. Five existing bank-admin rendering
  tests require a collected static manifest and failed before reaching application
  assertions. The focused 30-test competition suite is green.
- The 342-test Vitest run passed 340 tests. Two existing assertions in
  `registration-stages.svelte.spec.ts` failed after a generated SvelteKit
  `wrapDynamicImport` startup diagnostic. All 12 competition tests are green.
- Full `pnpm lint` stops on 16 pre-existing Prettier warnings outside the changed
  competition files. Focused Prettier and ESLint checks are green.

The remaining competition backlog covers double elimination, round robin, Swiss,
ordered-stage handoffs, qualification ties, and realtime delivery. Those are not
part of this first slice.
