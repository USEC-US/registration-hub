# Operating and testing Swiss competitions

Swiss is a qualifying stage. Configure a successor before publishing: fixed or threshold Swiss may be first or intermediate, including consecutive Swiss stages, but cannot be the final stage or name a champion. Configure the complete plan before the first public fixtures. Publication locks stage order, formats, points, tiebreaks, quotas, groups and allocation policies. Scheduling and series changes retain the existing before-play guards.

## Rules and fields

Fields contain 2–256 entrants. For N entrants, the round cap is `min(64, N - 1)` for an even field and `min(64, N)` for an odd field; each draw permits at most 16,384 ordinary matches. Fixed Swiss chooses either automatic `ceil(log2(actual N))` rounds or a custom integer from 1 to that cap. Automatic is saved as a policy, then resolved with each draw's actual incoming field; the recommendation does not guarantee distinct final positions. No recommendation-plus-two ceiling exists.

Fixed Swiss defaults to 3/1/0 points and opponent points, game difference, then games won. Match wins is optional. Choose Top-N from 2 through N. Complete every ordinary round, then resolve any tie crossing the cutoff by a confirmed manual decision or extra contests. No bye opponent or game score is fabricated; a bye grants normal win credit. Current standings count only finalized published current rounds.

Threshold Swiss requires decisive best-of matches and positive W/L targets with `W + L - 1` within the cap. W wins qualifies and L losses eliminates; all qualified entrants advance. A bye is a normal win. A double forfeit awards each entrant a loss and zero points. An unknown incoming field remains unknown in setup; the system never assumes half of the previous field, trims qualifiers or alters locked rules. If the actual field cannot fit a later stage's rules, generation blocks with an explanation. Automatic Round Robin group sizes fill each saved quota and balance the rest when the actual field arrives; exact sizes must match that field.

Every Swiss stage starts fresh: points, records, byes, opponent history and threshold status reset. Starting seeds order tied groups; handoffs use the existing saved random order. Previous-stage opponents may meet again.

## Organizer workflow

The organizer UI remains English under the user's 2026-10-13 scope clarification.
Translation of organizer controls is future work. Public Swiss rules, standings,
statuses and Changes support English and Vietnamese; the locale proof below
applies to those public views.

1. Save all stages and rules, choose approved entrants for stage 1, then save the seed order or random draw.
2. Review the private first-round preview and publish separately. Spectators cannot read a private draw. Refresh preserves the saved IDs and pairings.
3. Finalize every current-round match. Select **Generate next Swiss round** to save one private preview; GET and refresh never generate. Review its bye, score-group moves and any pairing exception, then select **Publish saved Swiss round**.
4. Pairing is all-or-nothing. If no complete round without rematches exists, follow **Allow required rematches**, tick the explicit confirmation and enter a private reason. Consent permits the minimum required repeats only after the complete no-rematch solution fails. The reason remains organizer-only. Unfinished rounds, stale revisions and private/historical score edits are rejected.
5. Finish fixed rounds and cutoff decisions, or threshold qualification/elimination. Generate the next stage's saved draw from exactly the immediately preceding stage's eligible qualifiers; review and publish separately.

Correction uses the existing signed preview and second confirmation with a private reason. Review the full Swiss rounds becoming historical, played results preserved, cutoff changes and affected downstream draws before confirmation. Later Swiss rounds become historical atomically and keep their scores. Source completion, eligible qualifier membership and saved fingerprints determine whether downstream draws survive. Invalidated downstream draws leave the active competition; played scores stay in public Changes history. Generate and publish replacement fixtures explicitly. Current standings exclude superseded rounds. Public history links target real Changes snapshots; numeric IDs distinguish repeated display labels.

## Synthetic fixtures

Use the existing development-only `seed_dev_data` command. `dev-usec-swiss` contains a nine-entry, four-round fixed-two-game Swiss Top-4 → single elimination chain, and a sixteen-entry W=3/L=3 threshold → automatic fixed Swiss Top-4 → single elimination chain. All qualifying stages are complete, playoffs are published with a played match, and any cutoff/repeat decision has an explicit synthetic private reason. Reruns preserve published draw/round/match IDs, limits and scores, unrelated tournaments and receiving payment settings. These teams are fictional; no personal workbook import is required.

## Proof and commands

Use PostgreSQL: SQLite runs skip locking races and cannot establish concurrency safety. The disposable test instance used `/tmp`, port 55441, database `hcmusec_swiss`, user `swiss_test`; the private test settings supply a test-only Turnstile key. All full logs are retained in `.superpowers/sdd/2026-10-10-swiss-stages/`.

```sh
cd server
UV_CACHE_DIR=/tmp/hcmusec-uv-cache PYTHONPATH=/tmp DJANGO_SETTINGS_MODULE=hcmusec_swiss_settings uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command --noinput
UV_CACHE_DIR=/tmp/hcmusec-uv-cache PYTHONPATH=/tmp DJANGO_SETTINGS_MODULE=hcmusec_swiss_settings uv run python manage.py check
UV_CACHE_DIR=/tmp/hcmusec-uv-cache PYTHONPATH=/tmp DJANGO_SETTINGS_MODULE=hcmusec_swiss_settings uv run python manage.py makemigrations --check --dry-run
uv run ruff check competitions e2e registrations/dev_seed.py registrations/tests/test_seed_dev_data_command.py
```

```sh
cd web
pnpm exec vitest run src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts src/lib/api/competitions.test.ts
pnpm check
pnpm build
DB_NAME=hcmusec_swiss DB_USER=swiss_test DB_PASSWORD= DB_HOST=/tmp DB_PORT=55441 pnpm exec playwright test --config=playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts
```

The browser harness overrides `DJANGO_SETTINGS_MODULE` with `config.settings`: its explicit `DB_*` environment is required even when the test settings prefix is present. It creates and destroys a unique test database and temporary media; do not point it at copied deployment credentials. Recollect Django staticfiles after organizer CSS/JavaScript changes. The browser DEBUG-only Turnstile bypass and Node color-environment notices are test-environment output.

Final workflow evidence: 335 PostgreSQL competition/development-seed tests in 461.738s, OK with no skipped races (`task-10-backend-recovery.log`, 2026-10-13). After restore, the original final backend process and disposable instance were gone and its log had no summary; the isolated `/tmp:55441` instance/settings were recreated and the entire gate rerun in this new log. The incomplete `task-10-backend-final.log` remains preserved and is not counted as passing evidence.

Both complete Django-backed bracket browser files passed all 12 journeys in 4.0m (`task-10-browser-final.log`, 2026-10-10), including fixed/threshold/consecutive Swiss, actual English organizer rematch consent, signed corrections after downstream play, public EN/VI and organizer/public 390px containment. Organizer Vietnamese localization was not exercised and is explicitly deferred. Frontend sources/build inputs were unchanged by the approved server compatibility fixes: retained Task 10 proof is 36 focused Vitest tests in 5.95s, Svelte/i18n with zero errors/warnings and a successful production build. Final Django system checks, migration drift, Ruff and browser ESLint passed. The production build retained third-party circular-dependency and empty-chunk warnings. This is the competition/seed gate and both bracket browser files, not the entire unrelated application suite.

Compatibility regressions retain saved Exact Round Robin group plans with unknown incoming counts and formerly published non-Swiss tiebreak navigation/scores. Restored history does not change current qualification or standings. Private retired rounds, superseded owning draws and Swiss superseded rounds remain excluded from current snapshots.

Task 1's populated PostgreSQL migration proof preserved existing elimination/Round Robin rows, played opponent slots, a stored bye, pending/superseded extra contests, tie lineage, source entries, codes and quotas (47 tests, 25.264s). The final gate also includes that regression.

The deterministic solver proof includes process/hash-seed checks. Task 2 measured Python 3.14.7 / NetworkX 3.7 pure solver performance: 256 first-round entrants paired in 0.304480s; a fragmented fixed field with 8,064 prior pairs over 63 rounds in 2.108597s; the analogous synthetic threshold records in 1.328945s. Each returned 128 pairs and zero repeats; cross-group pairs were 0, 64 and 2 respectively. These are observations, not worst-case guarantees. The threshold benchmark deliberately isolates matching and is not a legally playable full threshold tournament. Pinned NetworkX changes require rerunning determinism proof.

The consolidated final fix keeps full initial-draw and private-preview validation
while removing historical pairing replay from later publication. It also skips
completed automatic-result slot reads, resolves known automatic RR display sizes
without changing saved plans, and uses count-neutral English Changes copy.
Fresh proof: 340 PostgreSQL competition/seed tests in 357.049s with no skips,
46 focused command/workspace tests, and 25 public component tests. The complete
gate ran before a final display-only follow-up preserving configured Exact sizes
without selected entrants; that follow-up and its additional regression have
fresh 56-test workspace proof in 25.361s. It is not claimed as a 341-test full run.
Svelte/i18n, production build, Django check, migration drift, Ruff, scoped ESLint
and Prettier passed. The existing 12 browser journeys are retained evidence;
they were not rerun for this wave. The build retains the third-party warnings
described above.

The same disposable persisted 256-entry/64-round case contains 8,192 ordinary
fixtures with 63 completed 1–1 rounds and a saved private round 64. The real
`publish_swiss_round` now completed in **12.528s, 234 SQL executions and one solver
call (2.829933s solver time)**, ending PUBLISHED with its normal Changes event.
Fixture setup was **231.116s**, measured separately. The pre-fix review measured
**236.053s, 11,197 SQL executions and 64 solver calls (117.879s solver time)**,
excluding **242.478s** setup. Both runs use the unchanged
`/tmp/swiss_publication_review.py`, the pinned solver and separate disposable
database on `/tmp:55441`; the repeat ran without competing test/build processes.
Later historical fixture setup uses internal persistence with real pairings,
source fingerprints/audits and bulk finalized scores, so this is not an
end-to-end 8,192-result workflow. SQL and solver counters wrap real execution;
the timed publication is the actual command. The script removed its benchmark
database, and the disposable instance was stopped afterward. See the execution
workspace's `final-fix-report.md` and `final-fix-publication-measurement.log` for
commands and results. This is one local repeat-free case, not a worst-case or
production latency guarantee; pure solver timings alone remain insufficient for
persisted-publication claims.

## Migration and deployment

Migration `competitions.0005_swiss` adds round versions/visibility/fingerprints, saved limits and nullable automatic group sizes while preserving legacy published visibility and stored labels. Incomplete legacy Swiss setup stays private. Take a matching code/database backup before deployment. After Swiss data exists, reverting only code or reversing the migration is unsafe: use a forward fix or restore matching code and database backups. No deployment or live restore is part of this proof.

Withdrawal/disqualification, restoration and exceptional ending/reopening are now
implemented; see the [lifecycle operating and release guide](competition-lifecycle.md)
for fresh evidence, recovery and V1–V5 limits. Realtime/provider work remains deferred.
