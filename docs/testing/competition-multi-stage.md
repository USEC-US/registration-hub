# Operating and testing multi-stage competitions

A competition can contain ordered Round Robin, single elimination, double elimination and Swiss stages, including repeated formats. Swiss must have a successor and cannot crown a champion; see [the Swiss operating guide](competition-swiss.md). Configure every stage, group-size policy and outgoing quota before publishing stage 1. First publication locks the entire plan. Existing published single-stage competitions stay single-stage; this migration does not attach playoffs retroactively.

## Organizer workflow

1. Choose approved entrants for stage 1. Add and order the stages in Setup.
2. Set groups and advancement in **Stage Add/Edit**. For Round Robin, choose the number of groups and Exact or Automatic sizes, then name each group and choose its qualifiers. Exact sizes use entrant-count dropdowns; Automatic fills saved quotas and balances the remaining actual field. Unknown incoming fields stay unknown until the predecessor completes. Arbitrary partitions are supported, including `3/3/2`, `3/2/2`, and `2/5/3` with quotas `1/4/2`. Each group needs at least two entrants; a quota may equal its size. The form checks quotas, unique names and the incoming total when known. For an elimination stage preceding another stage, choose its Top-N quota; leave it empty for the final stage. The draw form only assigns entrants to the saved groups.
3. Save and preview stage 1, then publish. The entire chain must be valid before publication.
4. Finish every required source match, including groups advancing everyone. An unfinished two-team group still blocks generation even when both teams qualify.
5. Resolve a tie crossing a qualification cutoff using **Extra Matches** or **Manual Decision**. Harmless ties within an advancing band require no extra contest. Decisions belong to their source draw and are invalidated when their source changes. Undefined upper-bracket double-forfeit placement blocks any cutoff depending on that placement.
6. Select the next stage and generate its draw. The system uses exactly the immediately preceding stage's eligible qualifiers, shuffles once, and saves the draw. There is no ranking-based handoff order or same-group restriction. Elimination byes follow the saved random positions.
7. Review the private draw, regenerate explicitly if needed, then publish separately. Refreshing a preview never redraws it. Draft stages and replacement previews remain private.

A correction preview includes every affected downstream draw and its preserved result snapshots. Confirming a correction keeps the later draw only when the source remains complete and valid with exactly the same eligible qualifiers. Otherwise the dependent suffix becomes historical atomically. Its scores, entrant identities and first-publication timestamps remain stored. Retired published matches stay readable through their numeric API IDs; every mutation of a retired match is rejected. Spectators see **Awaiting replacement draw** until a new saved draw publishes.

New matches use labels such as `Groups1-M1` and `Playoffs-M1`. Numbering is continuous across a draw, extra matches append, and replacement draws restart at M1. Labels can repeat; numeric match IDs identify records. Legacy stored labels remain unchanged.

## Synthetic development data

Run the existing `seed_dev_data` command in a development environment. The `dev-usec-multi-stage` tournament contains three synthetic competitions with published groups and six-, six-, and seven-entry saved playoffs. Each has a played playoff result. Rerunning preserves published draw IDs, labels and scores. No personal workbook data is imported.

## Verification commands

Use PostgreSQL for the race tests; SQLite cannot prove row-lock behavior. Configure test-only Turnstile keys and run static collection if the manifest is missing.

```sh
cd server
uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command --noinput
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run ruff check competitions e2e registrations/dev_seed.py registrations/tests/test_seed_dev_data_command.py
```

```sh
cd web
pnpm exec vitest run src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts src/lib/api/competitions.test.ts
pnpm check
pnpm build
pnpm exec playwright test --config=playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts --grep multi-stage
```

The Django browser harness creates a unique disposable database and temporary media. Its private registration fixture writer remains unchanged. Browser journeys exercise plan locking, early handoff rejection, cutoff decisions, saved preview stability, publication, played-suffix retirement, historical privacy, stage/group controls, English/Vietnamese and containment at 390px.

## Local evidence (2026-10-10)

- 187 PostgreSQL competition and development-seed tests passed, including populated migration, all nine format combinations, Top-3 ties, three-stage chains, two played successor retirements, stable draws and concurrent operations.
- All 19 Django-backed organizer, spectator and registration browser journeys passed, including both new multi-stage journeys, English/Vietnamese and 390px containment.
- 28 focused frontend tests passed. Svelte/i18n checks reported no errors or warnings; the production build and changed-file ESLint passed.
- Django checks, migration drift and backend Ruff checks passed. Tests used a disposable PostgreSQL 18 instance and synthetic data, not the configured live database.

A fresh whole-feature reviewer found a future-stage workspace crash when the predecessor has no published draw. Regressions cover stage 1's private preview, an unpublished stage 2, and a retired predecessor; the waiting view now handles these states.

The Stage Add/Edit dropdown refinement passed 48 focused PostgreSQL organizer tests and both affected browser journeys, including 390px containment, saved dropdown values and live quota/total checks. Regressions cover unequal groups, atomic rollback, locked plans, route-owned stage targeting and format changes after incoming counts shrink. Django checks, migration drift, Ruff and changed-file ESLint passed; the full suites above were not rerun for this refinement.

Deferred minor: `Changes?stage=<id>` currently omits round-level series changes. The unfiltered Changes endpoint retains them; stored history is preserved.

## Swiss compatibility proof (2026-10-13)

The final Swiss gate extends this guide's earlier evidence: 335 PostgreSQL competition/development-seed tests passed in 461.738s (`task-10-backend-recovery.log`), with no skipped locking races. Both complete bracket browser files passed 12 journeys in 4.0m (`task-10-browser-final.log`, 2026-10-10), including the existing Round Robin and multi-stage flows. The unchanged frontend inputs retain 36 focused Vitest tests, clean Svelte/i18n checks and a successful production build; final Django checks, migration drift, Ruff and browser ESLint also passed. The incomplete pre-restore backend log is retained separately and is not passing evidence.

Regression proof preserves saved Exact group plans when the incoming field is unknown and retains formerly published non-Swiss tiebreak rounds, played scores and direct history navigation. Private retired rounds and retired owning draws stay out of snapshots/direct round reads. Historical rounds do not contribute to current standings or qualification; Swiss snapshots remain current-only. New fixtures cover fixed Top-4 → playoffs and threshold → automatic Swiss → playoffs, with stable reruns and stage-local resets.

The Swiss guide records populated migration and deterministic pure solver timings. Maximum-field/64-round persisted publication stress remains unmeasured, because publication revalidates retained rounds; pure matching measurements are not deployment latency guarantees.

## Migration and rollout

Migration `competitions.0004_multi_stage` adds group plans and draw provenance, backfills existing group rules and tie ownership, and preserves legacy codes and results. Take matching code/database backups before a live rollout. After multi-stage data is written, an older single-stage release cannot safely operate that database. Prefer a forward fix; a rollback requires restoring the matching backup rather than dropping the new columns and keeping newer writes. Local verification does not deploy or exercise a live restore.

Swiss is delivered in the subsequent slice documented in [competition-swiss.md](competition-swiss.md). Lifecycle removal/restoration and exceptional ending/reopening are delivered in the guide below. Provider integration and realtime updates remain deferred.

## Entrant and competition lifecycle

See the [lifecycle guide](competition-lifecycle.md) for withdrawal/disqualification,
restoration conflicts, locked qualifier shortfalls, exceptional ending/reopening,
historical fixture visibility and matching code/database recovery.
