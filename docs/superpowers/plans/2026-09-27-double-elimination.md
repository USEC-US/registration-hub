# Double Elimination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a standalone double-elimination competition through the existing
organizer workspace and public bracket, including both grand-final policies and
safe correction after downstream play.

**Architecture:** Extend the existing elimination generator, persisted slot
dependencies, and guarded competition commands. Reuse the organizer workspace,
public HTTP endpoints, and Svelte match cards; add upper/lower/finals sections.
Keep progression and correction in the competition domain.

**Tech Stack:** Django, PostgreSQL, Django Unfold, DRF, Python standard library,
SvelteKit, Paraglide, Vitest, and Playwright. No new dependency.

**Spec:** [Approved competition-core design](../specs/2026-09-23-competition-core-design.md),
especially Sections 5–6 and 10–13.

**Status:** Approved for subagent execution and implemented on 2026-09-27.
Focused verification and operating details are recorded in the
[double-elimination testing guide](../../testing/competition-double-elimination.md).

## Global Constraints

- Preserve `tournaments` catalogue ownership and `registrations` eligibility,
  payment, and identity-snapshot ownership; `competitions` owns mutations.
- Lock `TournamentGame → Competition → affected rows`; check the competition
  revision and write state/history in the same transaction.
- Support 2–256 entrants and at most 16,384 generated regular matches per draw.
- Best-of lengths are positive and odd. Resolve match override → round override
  → stage default; retain the applied length once play starts.
- Publication locks format, seeds, routing, and reset/no-reset policy.
- Expose only published, explicitly allowlisted fields. Contact information,
  real names, student IDs, payment data, actors, and internal notes stay private.
- Preserve current single-elimination behavior, match IDs, URLs, and history.
- Keep normal HTTP, manual scheduling, and existing organizer permissions.
- Preserve the pre-existing uncommitted seed changes. The private source ODS is
  reference input, not a committed fixture or application runtime dependency.

## Observable acceptance and boundaries

An organizer can choose single or double elimination during setup. For double
elimination they explicitly choose reset or no reset, save manual/random seeds,
preview both brackets and finals, publish, schedule, and enter results. Winners
and losers reach their saved destinations exactly once. A lower-bracket loss
eliminates; byes never create a loser. The applicable final completes with a
champion or an explicit no-champion outcome.

A signed correction preview includes changed upper/lower/final participants,
played results that must reset, and reset-final activation changes. Confirmation
updates all affected state atomically and preserves prior public results and
private organizer history. Unaffected contests retain their results.

Spectators see upper/lower/finals sections, source winner/loser labels, the
grand-final policy, schedules, effective series lengths, results, and Changes
in English/Vietnamese, with keyboard and mobile access.

This completes E3/E4 and their organizer/public/verification portions in
[BRACKET-TODO](../../BRACKET-TODO.md). Round robin, Swiss, stage handoffs,
qualification ties, withdrawal/disqualification commands, TFT, and realtime
remain later slices. Existing forfeit/double-forfeit outcomes are in scope.

## Verified workbook reference

Source: `docs/MASTER PLAN - FPT SHOP UNI TOUR 2026.ods`.
SHA-256: `907a1b8dfca37434929f48313aba898a0a64b9f22a2268cb0b2fb26e907dbfc2`.
Inspected locally with Python `zipfile` and `xml.etree.ElementTree`.

The `BẢNG ĐẤU LQM MIỀN NAM` worksheet records a **single-elimination** bracket:

| Evidence | Verified structure |
| --- | --- |
| Rows 4–5, match numbers 1–8 in columns B/G/L/Q | 16 distinct team labels, 8 opening matches, BO1 |
| Rows 10–11, matches 9–12 | 4 quarterfinals, BO1 |
| Rows 17–18, matches 13–14 | 2 semifinals, BO3 |
| Row 24, match 15 | Final, BO3 |
| Score cells across these matches | Five 1–0, seven 0–1, two 0–2, one 1–2 |

Reuse field size and series variation, with invented team/roster identities and
synthetic results. Double-elimination routing and results are **synthetic** and
validated against the approved design, not represented as historical tournament
results. Do not import roster/contact/check-in sheets or TFT data. Tests and seeds
must run without the workbook present.

## Review Focus

1. Uneven fields: a known-empty upper slot creates no lower entrant; an unknown
   opponent must never be treated as a bye. Tasks 1–2.
2. Two entrants: no lower match exists; the upper loser goes directly to the
   grand final, with an optional reset. Tasks 1–2.
3. A correction can deactivate an already-played reset final, reopen a completed
   stage, or change both routes without resetting an unrelated match. Task 3.
4. Double forfeits send neither entrant onward; structural final byes do not
   trigger a reset, and an empty deciding final yields no champion. Task 2.
5. A setup change after saving a draft must not publish obsolete routing; direct
   POSTs must not start an inactive reset or bypass permissions/revisions. Tasks 2–4.

## Task 1: Represent and generate both elimination brackets

**Files:** modify `server/competitions/elimination.py`, `models.py`,
`tests/test_elimination.py`, and `tests/test_models.py`; create
`server/competitions/migrations/0002_double_elimination.py`.

**Interfaces:**

- Keep `generate_single_elimination(entrant_count: int)` and its seed ordering.
- Add `generate_double_elimination(entrant_count: int, *, grand_final_policy: str)
  -> tuple[GeneratedRound, ...]` using `RESET` or `NO_RESET`.
- Extend `GeneratedRound` and `WinnerSlot` with `section: str = "NORMAL"`;
  add `LoserSlot(round_number: int, match_number: int, section: str)`.
  `GeneratedMatch.slots` accepts seed, winner, or loser sources.
- Add `Round.Section.UPPER`, `LOWER`, and `FINALS`; round numbers are local to
  each section. Preserve `NORMAL` for single elimination.
- Add `MatchSlot.SourceOutcome.LOSER` and `Stage.grand_final_policy` (blank for
  other formats, required `RESET`/`NO_RESET` for double elimination).
- Add `Match.Status.CONDITIONAL` and `NOT_REQUIRED` for the reserved reset match;
  neither is a played result, bye, or no-champion outcome.
- Constrain policy to `RESET`/`NO_RESET` for double elimination and blank for
  other formats. A slot with a source match requires WINNER/LOSER; a direct or
  empty slot requires blank `source_outcome`.

- [x] Write generator assertions for exact 2/4/8/16 routing, including
  `lower_round_count == 2 * log2(N) - 2` for N >= 4, and 0 for N=2.
  For a full field, total matches are `2*N-2` with no reset and `2*N-1`
  including the reserved reset. Assert the 8-team lower drop round uses upper
  round 2 losers in reversed match order, not a redraw.
- [x] Run `cd server && uv run python manage.py test competitions.tests.test_elimination competitions.tests.test_models --keepdb`;
  confirm the new expectations fail before implementation.
- [x] Implement Section 6's exact routing: adjacent upper-R1 losers, reversed
  drop rounds alternating with lower merge rounds, then finals. Reuse the
  existing seeded upper generator. The first final has upper winner in slot 1
  and lower winner in slot 2; for N=2 slot 2 is the upper loser. Under RESET,
  reserve finals round 2 with first-final loser/winner sources in slots 1/2.
- [x] Test 3/5/6/9/17/256 entrants, acyclicity, unique destinations, missing seeds,
  and no duplicate participant within a section's round. Test the new policy
  and slot-source database constraints; existing rows retain their values.
- [x] Generate/review the migration. Re-run the focused tests and
  `uv run python manage.py makemigrations --check --dry-run`; require green tests
  and no unrecorded model changes. Commit only this task's files.

Migration review addition: the old schema allowed double-elimination stage rows
although supported commands created only single elimination. Backfill any such
legacy rows with `RESET` before adding the policy constraint, and test upgrading
from migration 0001. New double-elimination setup still requires an explicit policy.

## Task 2: Configure, persist, and operate double elimination

**Files:** modify `server/competitions/commands.py`; update its callers in
`admin.py`, `tests/test_commands.py`, `tests/test_api.py`, `tests/test_workspace.py`,
`tests/test_concurrency.py`, `server/registrations/dev_seed.py`, and
`server/e2e/serve.py`; create
`server/competitions/tests/test_double_elimination_commands.py`.

**Interfaces:** rename the internal, repository-owned setup/draw commands to:

```python
configure_elimination(
    *, actor, competition_id: int, expected_revision: int, name: str,
    default_series_length: int, format: str, grand_final_policy: str = "",
) -> Stage

save_elimination_draw(
    *, actor, competition_id: int, expected_revision: int,
    entrant_order: Sequence[int] | None = None, randomize: bool = False,
) -> StageDraw
```

Both existing and new callers use these commands. Setup accepts only the two
implemented elimination formats; draw generation reads the saved format/policy.
`publish_draw`, scheduling, overrides, progress, start, and finalization retain
their existing signatures and authorization boundary.

- [x] Add failing command tests for 2/4/5/8 entrants under both policies. Assert
  an upper played/forfeit loser fills only its lower source, a lower loss exits,
  unresolved sources stay unresolved, and automatic byes have null scores.
- [x] Run the new module with `uv run python manage.py test competitions.tests.test_double_elimination_commands --keepdb`.
- [x] Share setup/persistence between formats; migrate all callers, explicitly
  passing `SINGLE_ELIMINATION` from existing setup paths. Persist matches before
  linking source slots. Include section in new double-elimination match codes;
  preserve existing single-elimination code generation.
- [x] Supersede a saved draft when format or final policy changes; retain its
  history and require a new draw. Publication checks that saved routing matches
  current format/policy, has valid same-draw sources, and is acyclic.
- [x] Resolve dependencies in topological order using `graphlib.TopologicalSorter`,
  never section-local round number alone. Share that ordering with correction.
  Winner routes use the winner; loser routes use the other entrant only for
  played/forfeit results. BYE, EMPTY, and DOUBLE_FORFEIT have no losing entrant.
- [x] Reconcile the reserved final before automatic completion: CONDITIONAL
  while first-final sources/results are unresolved; PENDING only when the lower
  entrant beats the upper entrant by PLAYED or FORFEIT; otherwise NOT_REQUIRED
  once the first final ends. Skip inactive finals during automatic resolution.
  Reject starting, scoring, or finalizing inactive finals in commands. A reserved
  final may be scheduled and given a valid series override before activation.
- [x] Select the deciding final explicitly by section/policy/activation. Under
  no reset, the first final decides the stage. Under reset, an activated second
  final must finish; otherwise the first final decides it. Empty/double-forfeit
  deciding finals complete without a champion; structural byes never trigger reset.
- [x] Test publication locks, stale/repeated actions, missing/invalid policy,
  format switches after preview, automatic paths, and unchanged series precedence.
  Simulate complete full/uneven fields with both policies: no entrant disappears
  after one normal loss except at the declared no-reset final; a second normal
  loss eliminates, and each stage terminates. Exercise both an upper-winner and
  lower-winner first final, plus forfeits/double forfeits on each route.
  Run the new module plus `competitions.tests.test_commands` and
  `competitions.tests.test_concurrency`; require green results, then commit.

## Task 3: Correct results across both brackets and finals

**Files:** modify `server/competitions/commands.py`,
`tests/test_double_elimination_commands.py`, and `tests/test_concurrency.py`.

**Interfaces:** retain `preview_correction`, `review_correction_preview`, and
`apply_correction`; extend their signed impact with explicit reset-final state
changes. Continue treating client-supplied impact as untrusted.

- [x] Write tests that complete a 4-team reset bracket, then change an upper
  result. Assert the preview includes affected lower and final contests, the
  confirmed transaction clears their started/applied/result fields, and previous
  scores remain in Changes. Assert unaffected matches keep their results.
- [x] Add tests where correcting the first final activates a reset, where a
  correction deactivates an already-played reset, and where a score-only edit
  with unchanged routed entrants preserves every downstream result.
- [x] Run those tests and confirm failures before implementing the new impact.
- [x] Project winner/loser participants and reset activation in memory in
  dependency order, using the same routing/activation rules as normal progression.
  Compare ordered participants and activation with saved state; propagate resets
  only where results become invalid. Recompute the exact projection under locks
  at confirmation. Include activation/deactivation in the signed payload and
  public/private history even if the reserved final has never been played.
- [x] Add PostgreSQL races for finalizing the same upper match twice and applying
  a stale correction after a downstream result. Require one accepted revision,
  atomic winner/loser destinations, no duplicate history, and no partial reset.
- [x] Run `uv run python manage.py test competitions.tests.test_double_elimination_commands competitions.tests.test_commands competitions.tests.test_concurrency --keepdb`;
  require green results, then commit.

## Task 4: Extend the existing organizer workspace

**Files:** modify `server/competitions/forms.py`, `admin.py`,
`admin_workspace.py`, `templates/admin/competitions/workspace.html`,
`templates/admin/competitions/match_detail.html`,
`templates/admin/competitions/action_form.html`, and `tests/test_workspace.py`.

**Interfaces:** `CompetitionSetupForm` submits `format` and
`grand_final_policy` to Task 2. `slot_label` distinguishes winner/loser sources;
`match_card` exposes inactive-final state and only valid actions. Keep existing
admin URLs and POST/CSRF patterns.

- [x] Add failing workspace tests for setup through publication, both final
  policies, distinct upper/lower/finals headings, and source winner/loser labels.
  Assert no result action appears on CONDITIONAL/NOT_REQUIRED matches.
- [x] Run `uv run python manage.py test competitions.tests.test_workspace competitions.tests.test_admin --keepdb`.
- [x] Offer only single/double elimination in setup; require an explicit final
  policy for double elimination. Replace hardcoded single-elimination action
  copy and flat final/semifinal inference with section-aware presentation.
  Show the policy in preview/publication and reserved-final activation text.
- [x] Display correction activation/deactivation alongside affected result
  resets, including the private internal reason only where authorized.
- [x] Test direct inactive-final POSTs, missing model permissions, stale forms,
  CSRF enforcement, and GET requests that leave revision/state unchanged.
  Assert scheduling/series overrides work on the reserved conditional final
  while starting/scoring it remains forbidden until activation.
  Re-run workspace/admin tests; require green results, then commit.

## Task 5: Publish and render double-elimination brackets

**Files:** modify `server/competitions/serializers.py`, `views.py`, and
`tests/test_api.py`; `web/src/lib/api/types.ts`,
`web/src/lib/api/competitions.test.ts`,
`web/src/routes/tournaments/[slug]/games/[gameId]/bracket/+page.svelte`,
`web/src/routes/bracket-page.test.ts`,
`web/src/routes/bracket-page.svelte.spec.ts`, and `web/messages/{en,vi}.json`.

**Interfaces:** add explicitly allowlisted `grand_final_policy` to public stage
data and `source_outcome` to public slots; extend the match-status union for
CONDITIONAL/NOT_REQUIRED. Reuse existing `section`, `source_match_id`, match
codes, and endpoints. Expose correction activation changes through safe public
fields, with private actor/reason fields excluded.

- [x] Add API assertions for policy, section, winner/loser sources, conditional
  states, published-only reads, safe Changes, and unchanged single-elimination
  fields. Extend component fixtures for reset waiting/active/not-required states.
- [x] Run API and focused bracket UI tests to observe the new failures.
- [x] Group existing cards into upper/lower/finals sections for desktop and
  mobile. Resolve source labels through existing match IDs/codes. State reset
  versus no-reset rules and distinguish a conditional/not-required final from a
  bye or completed match. Preserve keyboard scrolling, time zones, refresh,
  champion/no-champion states, and EN/VI parity. Keep single-elimination layout.
- [x] Render correction before/after outcomes, affected matches, and final-state
  changes in public Changes; reuse safe snapshot fields already available where
  possible. Do not reduce a reset to an unexplained generic change label.
- [x] Run `uv run python manage.py test competitions.tests.test_api --keepdb` in
  `server`; in `web`, run `pnpm check` and
  `pnpm test:unit --run src/lib/api/competitions.test.ts src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts`.
  Require green results, then commit.

## Task 6: Synthetic fixtures and a real browser journey

**Files:** extend `server/registrations/dev_seed.py`,
`server/registrations/tests/test_seed_dev_data_command.py`, `server/e2e/serve.py`,
`web/e2e/django/admin-bracket.spec.ts`, and `web/e2e/django/bracket.spec.ts`;
update `server/README.md`, `docs/BRACKET-TODO.md`, and `docs/TODO.md`; create
`docs/testing/competition-double-elimination.md`.

**Interfaces:** extend `seed_dev_data` through competition commands. Preserve
existing sponsor/Chess/LoL scenarios and their uncommitted changes. Add one
command-owned `dev-usec-double-elimination` tournament: a published, ready,
16-team reset division and a completed 5-team no-reset division. Use existing
game catalogue entries and wholly synthetic roster/contact snapshots.

- [x] Add seed assertions for rerun stability, preserved unrelated records,
  both policies, odd-field byes, published sections, and valid approved entrants.
  Seeds work with the source workbook absent. The 16-team fixture uses stage
  BO1 with upper semifinals/final, lower final, and finals overridden to BO3;
  this double-elimination series allocation is explicitly synthetic.
- [x] Implement fixtures via the same configure/select/draw/publish/result
  commands as organizers, with current revisions after each mutation. Reuse the
  existing seed guard and cleanup ownership; never reset non-fixture data.
- [x] Add a disposable 4-team browser scenario: organizer setup → seed → private
  preview → publish → upper/lower results → lower entrant wins first final →
  reset final completes → correction preview/confirmation invalidates that
  reset. Verify public refresh reflects the resulting state/history without the
  private reason. Use isolated data so existing browser journeys remain stable.
- [x] Exercise public EN/VI, keyboard focus, and a 390-pixel mobile viewport;
  assert no page overflow and clearly labeled upper/lower/finals sections.
- [x] Run the focused checks below, record actual outcomes and any environment
  limits, then document organizer operation, seed commands, and migration safety.
  Mark only delivered E3/E4 and applicable sub-slices complete. Commit only the
  task's own changes; review pre-existing seed edits by intent before staging.

## Final focused verification

Use the existing PostgreSQL test configuration and `--keepdb`. If system checks
require a Turnstile key under `DEBUG=False`, supply a test-only value. Collect
static assets if the admin test environment lacks its manifest. Distinguish
environment failures from application failures; do not claim SQLite proves races.

```bash
# server/
uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command --keepdb
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run ruff check competitions registrations/dev_seed.py registrations/tests/test_seed_dev_data_command.py e2e/serve.py

# web/
pnpm check
pnpm test:unit --run src/lib/api/competitions.test.ts src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts
pnpm exec playwright test --config playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts
pnpm build

# repository root
git diff --check
```

Also run Prettier/ESLint on changed frontend files. Broaden checks only when a
failure or changed shared behavior requires it. Recorded outcomes: 89 focused PostgreSQL tests, 16 focused frontend tests, and
four real Django/Svelte browser scenarios passed. Migration drift, system checks,
changed-file lint/formatting, and the production build passed. The testing guide
records exact scope and environment warnings.

The additive migration preserves single-elimination rows. Once real double-
elimination data exists, rolling back application code alone is unsafe because
older commands do not understand loser slots or conditional finals. Prefer a
forward fix, or restore a matching database/application backup. Do not describe
reversing enum/field changes as a safe rollback of populated brackets.

## Execution record

The user approved subagent execution. Shared generation, persistence, progression,
and correction landed sequentially; organizer and public work used the reviewed
contracts independently. The integration owner retained migrations, command
contracts, task-only staging, and verification. Existing sponsor-fixture edits
remain in the worktree; the existing team helper required by the new seeds is
included with this slice. The private workbook remains untracked.
