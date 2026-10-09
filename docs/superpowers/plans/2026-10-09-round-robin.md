# Round Robin Groups and Qualification Ties Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let organizers run single/double round robin groups, operate matches,
inspect standings, resolve qualification ties, and publish the same information
to spectators through the existing competition workspace.

**Architecture:** Keep competition mutations in `server/competitions`. Add pure
round robin calculations and a round robin command module; share the existing
lock/revision/history boundary and match lifecycle with elimination. Extend the
current Unfold workspace and allowlisted HTTP snapshots, using computed standings
rather than a second persisted standings table.

**Tech Stack:** Django, PostgreSQL, Django Unfold, DRF, Python standard library,
SvelteKit, shadcn-svelte, Paraglide, Vitest, and Playwright. No new dependency.

**Spec:** [Approved competition-core design](../specs/2026-09-23-competition-core-design.md),
especially Sections 3–5, 7, 9–13.

**Status:** Approved for native implementation on 2026-10-09. Scope selected on 2026-10-09: round robin groups,
standings, qualification ties, organizer controls, and public views. Stage handoffs
are the next slice. All eight tasks are implemented. The fresh review findings are fixed; final verification is recorded in the operating guide.

## Global Constraints

- Preserve `tournaments` catalogue ownership and `registrations` eligibility,
  payment, and identity snapshots; `competitions` owns competition mutations.
- Support 2–256 entrants per stage and at most 16,384 regular generated matches
  per draw. Bound extra tiebreak match generation separately by the same budget.
- Every group has at least two entrants. Single/double round robin means exactly
  one/two meetings per pair, independently of series length.
- Best-of N is positive and odd. Fixed N games is positive; final scores sum to N
  and equal scores are a draw. Tiebreak matches always use decisive best-of rules.
- Resolve match override → round override → stage default; freeze applied mode
  and length at start. Scheduling alone does not start a match.
- Points are nonnegative decimals with two fractional digits: `win > draw >= loss`.
  Default points are win 3 / draw 1 / loss 0.
- Default tiebreak order is head-to-head points → game difference → games won.
  The supported additional criterion is match wins. Criteria cannot repeat.
- Head-to-head uses the mini-table of the entrants still tied at that criterion.
  Continue to the next criterion after separation; do not restart head-to-head.
- Forfeits award normal win/loss points; double forfeits award zero to both.
  Only completed played series contribute game metrics. Odd-group rests award
  no points, wins, losses, or fabricated game scores.
- Publication locks membership, meetings, series mode, points, tiebreak order,
  and qualifying places. Keep valid before-play length overrides and scheduling.
- Lock `TournamentGame → Competition → affected rows`, check revision, and commit
  state plus attributable history together. Corrections require signed previews.
- Expose only published, explicitly allowlisted display data. Exclude actors,
  internal reasons, registration/payment/contact data, credentials, real names,
  birth dates, and student IDs from responses and page data.
- Preserve elimination behavior, existing IDs/URLs, and retained history. GET
  requests neither generate fixtures nor persist standings or tie decisions.
- Normal HTTP, manual scheduling, English/Vietnamese, keyboard access, and mobile
  presentation remain required.

## Acceptance and boundaries

An organizer configures round robin, chooses one or two meetings and a series
mode, selects approved entrants, assigns named groups manually or by seeded snake
allocation, previews the saved fixtures and rules, then publishes. A saved random
ordering is available before snake allocation and is never regenerated on GET.
Each group has a before-publication qualifying-place count, initially one.

Standings use final results only. Rows show played/won/drawn/lost, points, games
won, game difference, tied rank, and qualification state. Pending play is clearly
provisional. Equal ranks remain equal after configured criteria; stable seed
display order never decides a qualifying place. Only a tie crossing a qualifying
cutoff requires resolution; a tie wholly inside or outside that cutoff does not
prevent the group from completing.

The organizer can resolve a cutoff tie by an ordered manual decision with a
private reason, or extra contests. Two tied entrants play one decisive match;
three or more play a single round robin mini-table, ranked by match wins,
head-to-head wins, then game difference. These results do not change ordinary
group points. A remaining cutoff tie requires another explicit resolution.

The stage completes after all required regular play and cutoff resolutions.
Multiple groups do not acquire an invented overall champion. A sole group with
one qualifying place may expose its resolved first-place entrant as champion;
other completed group stages expose their ordered group qualifiers. The existing
exceptional `completed_without_champion` flag must not label an ordinary group
stage as an elimination bracket with no winner.

Corrections recompute standings and preview changed qualifiers, invalidated tie
decisions, and affected extra contests. Preserve unrelated ordinary match results.
Superseded extra contests retain their IDs/results as historical data and cannot
be operated as current matches. Confirm replacement tie play explicitly.

This slice covers G1/G2, the round robin portions of H2/A6/A7/P3, and associated
verification/delivery in [BRACKET-TODO](../../BRACKET-TODO.md). H1, Swiss, ordered
stage navigation/handoffs, withdrawal/disqualification commands, TFT, and realtime
remain open. The shared match command still supports explicit forfeit and double
forfeit. No participant or workbook personal data is imported.

## Operator configuration of standings rules

**Stage Setup menu:** Approved by the user on 2026-10-09. The approved controls
are configurable win/draw/loss points and four optional ordered tiebreaker
dropdowns, with saved rules visible in preview/public views and locked on publication.

Configure these rules in the stage's existing Setup action before publication.
They apply to every group in that stage. Match points are always the primary
ranking criterion; the operator separately sets win/draw/loss points, initially
3.00/1.00/0.00, with the precision and ordering validation above.

Use four numbered optional dropdowns, labelled **Tiebreaker 1** through
**Tiebreaker 4**. Each offers **No rule**, **Head-to-head points**, **Match wins**,
**Game difference**, and **Games won**. Defaults are head-to-head points, game
difference, games won, and No rule. Selecting a criterion in an earlier position
makes it higher priority. Ignore unused positions when saving and preview the
result as one compact ordered list. Server validation rejects duplicate criteria
and unsupported values. All positions may be unused, leaving point ties for
explicit resolution where they cross the qualifying cutoff.

Display short explanations beside the controls: head-to-head points considers
only matches among the entrants currently tied; match wins includes played and
forfeit wins; game difference is completed played game wins minus losses; games
won counts completed played game wins. Live and partial forfeit game scores do
not contribute game metrics. Apply each criterion only to the entrants still
tied, without recursively restarting head-to-head after splitting a tied set.

Show the saved points and ordered criteria in the private draw preview and
published rules. After publication, render them read-only and reject direct POST
attempts to change them. Custom formulas, scripts, per-group variants, and
configurable head-to-head recursion are outside the approved rules for this slice.

For extra tie contests, the operator chooses an odd best-of length, initially
one. A multi-entrant mini-table retains the approved fixed ranking order of match
wins → head-to-head wins → game difference. Its criteria are not the ordinary
group's configurable list. Manual decisions and still-unresolved mini-table ties
follow Task 4's recorded confirmation workflow.

## File ownership and dependency order

One integration owner controls models/migrations, shared command helpers, shared
match lifecycle, serializers, and TypeScript contracts. Tasks 1–4 are sequential;
Tasks 5 and 6 are independent once Task 4 contracts are fixed. Task 7 follows
Task 5; Task 8 verifies the assembled work after Tasks 6 and 7.
The execution method is selected when this written plan is reviewed.

| Files | Responsibility |
| --- | --- |
| `server/competitions/round_robin.py` (new) | Pure allocation, circle schedule, standings, tie criteria |
| `server/competitions/command_support.py` (new) | Existing division/root lock, revision check, history/snapshots, shared length validation |
| `server/competitions/round_robin_commands.py` (new) | Group setup/draw, standings read, tie decisions, projected correction effects |
| `server/competitions/models.py`, `migrations/0003_round_robin.py` | Rules, group membership, tie records, mode snapshots, additive migration |
| `server/competitions/commands.py` | Shared scheduling/progress/finalization/correction integration |
| `server/competitions/forms.py`, `admin.py`, `admin_workspace.py`, templates/static files | Extend the current organizer workflow |
| `server/competitions/serializers.py`, `views.py`, `web/src/lib/api/types.ts` | Published snapshot and explicit public history contracts |
| `web/src/routes/tournaments/[slug]/games/[gameId]/bracket/+page.svelte`, `web/messages/{en,vi}.json` | Group selector, standings, rounds, rules, Changes |
| Existing competition, migration, seed, Vitest, and Django Playwright suites | Focused proofs and elimination regression coverage |

## Review Focus

1. Unequal and odd groups: all pairs meet the configured number of times, no
   entrant plays twice in a group round, and rests never become scored byes. Task 1.
2. A fixed-game draw and a partial-score forfeit produce different game metrics;
   a double forfeit cannot accidentally become a draw. Tasks 1 and 3.
3. A three-way head-to-head tie separates once and continues with the remaining
   criteria, with no seed-based qualifier or recursive restart. Tasks 1 and 4.
4. A score correction retaining the same winner can invalidate a tie resolution
   or its nested extra contests; winner-routing comparison alone is insufficient.
   Task 4, including PostgreSQL stale-preview/concurrency tests.
5. Old fixture shapes and superseded tie matches remain readable without leaking
   private decisions or exposing historical matches as current scoring targets.
   Tasks 2, 5, 6, and 8.

## Task 1: Pure group scheduling and ranking

**Files:** create `server/competitions/round_robin.py` and
`server/competitions/tests/test_round_robin.py`.

**Interfaces:**

- `allocate_snake_groups(ordered_ids: Sequence[int], group_count: int)
  -> tuple[tuple[int, ...], ...]`.
- `generate_round_robin(entry_ids: Sequence[int], *, meetings: int)
  -> tuple[RoundRobinRound, ...]`; `RoundRobinRound` contains `number`,
  `pairings: tuple[tuple[int, int], ...]`, and `resting_entry_id: int | None`.
- `rank_group(entry_ids: Sequence[int], results: Sequence[RoundRobinResult], *,
  points: tuple[Decimal, Decimal, Decimal], tiebreaks: Sequence[str])
  -> tuple[Standing, ...]`.
- `RoundRobinResult` contains match/side IDs, outcome, scores, and winner ID;
  callers supply confirmed final results only. `Standing` contains entry ID,
  rank, played/wins/draws/losses, Decimal points, games won, and game difference.
- Criterion identifiers: `HEAD_TO_HEAD`, `MATCH_WINS`, `GAME_DIFFERENCE`,
  `GAMES_WON`. Final equal ranks use competition ranking (1, 1, 3).

- [x] **Write failing algorithm tests.** Name tests
  `test_circle_pair_counts_and_reversed_second_cycle`,
  `test_odd_group_rest_has_no_match`, `test_snake_allocation`, and
  `test_head_to_head_does_not_restart_after_subgroup_separates`.
  Assert 3/4/5-entry single schedules have 3/6/10 matches and double schedules
  6/12/20; each pair meets once/twice; each second-cycle pairing reverses sides;
  each entrant plays at most once per round. Eight ordered seeds in two snake
  groups yield `(1, 4, 5, 8)` and `(2, 3, 6, 7)`.
- [x] **Add standings fixtures.** `test_draw_forfeit_and_double_forfeit_metrics`
  gives a fixed-two-games 1–1 draw one point each; a forfeit gives 3/0; a double
  forfeit gives 0/0 and two losses. Recorded partial forfeit scores add no game
  metrics. `test_equal_ranks_do_not_use_seed_to_break_cutoff_tie` preserves ties.
  Include exact decimal points such as 2.50/0.75/0.25 and different group sizes.
- [x] **Run red:** from `server/`,
  `uv run python manage.py test competitions.tests.test_round_robin`.
  Expect failure for missing calculations before implementation.
- [x] **Implement the declared calculations.** Use the circle method with an
  empty rotating position for rests, and tied-set refinement for each ranking
  criterion. Keep deterministic display order separate from rank equality.
- [x] **Run green:** the same command must pass, including supported bounds,
  duplicate IDs, invalid meetings, invalid group sizes, and no-rematch counting.
- [x] **Commit only Task 1 files** as `feat(competitions): calculate round robin schedules and standings`.

## Task 2: Persist rules, memberships, and reviewed draws

**Files:** modify `server/competitions/models.py`, `commands.py`,
`tests/test_models.py`, `tests/test_migrations.py`; create
`command_support.py`, `round_robin_commands.py`,
`migrations/0003_round_robin.py`, and `tests/test_round_robin_commands.py`.

**Interfaces:**

- Move `_lock_competition`, `_check_revision`, `_record_change`,
  `_match_snapshot`, and `_validate_best_of` unchanged into `command_support.py`,
  importing them into existing and new command modules. Keep all existing external
  command signatures. The round robin module must not import `commands.py`, since
  the shared lifecycle imports its group functions. Do not create a dispatch framework.
- Add `_validate_series_length(mode: str, length: int) -> None` in that shared
  helper module, retaining best-of validation and allowing positive fixed lengths.
  Add `Match.effective_series_mode`, resolving applied mode → round mode override
  → stage mode, alongside the existing effective length property.
- Add Stage meetings, Decimal win/draw/loss points, and ordered tiebreak fields.
  Add `StageGroup(draw, number, name, qualifying_places)` and nullable
  `StageEntry.group` / `Round.group` references, protected from deletion.
  Enforce unique group numbers per draw and positive qualifying places in the
  database; validate places against membership size under the command lock.
- Keep legacy unique ungrouped rounds with a conditional `(draw, section, number)`
  constraint; add grouped uniqueness `(draw, group, section, number)`.
  Commands enforce that groups/entries/rounds belong to the same draw.
- Add `TieResolution(group, parent, method, state, source_fingerprint,
  contenders, decision_order, created_at, confirmed_at)`; contenders are an M2M
  to StageEntry, decision_order is an immutable ordered-ID snapshot, methods are
  `MANUAL`/`EXTRA_MATCHES`, states
  `PENDING`/`AWAITING_RESOLUTION`/`CONFIRMED`/`SUPERSEDED`.
  Add `places` for the cutoff being resolved and nullable `Round.tie_resolution`.
  Parent is a protected nullable self-reference for a remaining tied subset.
  Completed extra contests with a remaining cutoff tie use AWAITING_RESOLUTION;
  a confirmed nested choice resolves that subset and recomputes its parent.
- Add `Round.series_mode_override` (blank or `BEST_OF`, tiebreak rounds only)
  and `Match.applied_series_mode`. Backfill started legacy matches from their
  stage mode; retain all match IDs, scores, history, and frozen lengths.
- `configure_round_robin(*, actor, competition_id: int, expected_revision: int,
  name: str, meetings: int, series_mode: str, default_series_length: int,
  win_points: Decimal, draw_points: Decimal, loss_points: Decimal,
  tiebreaks: Sequence[str]) -> Stage`.
- `save_round_robin_draw(*, actor, competition_id: int, expected_revision: int,
  group_specs: Sequence[tuple[str, int]], ordered_entrant_ids: Sequence[int],
  memberships: Sequence[Sequence[int]] | None = None, randomize: bool = False)
  -> StageDraw`. Group specs are `(name, qualifying_places)` in display order.
  Explicit memberships mean manual allocation; otherwise use snake allocation.
  Reject randomization with manual memberships; save the exact random order once.
- Reuse `select_entrants` and `publish_draw`; branch saved-draw validation by
  format, verifying exact pair coverage and all rule/membership invariants.

- [x] **Write failing persistence tests.** Cover manual unequal 3/5 groups,
  snake allocation, saved random refresh, group sizes under two, duplicate/missing/
  cross-division entrants, invalid/nonfinite point precision/order, repeated criteria,
  qualifying places outside `1..group_size`, and the generated match budget.
  Assert changing setup or entrants supersedes an obsolete draft before publish.
- [x] **Write the migration test.** Upgrade populated `0002_double_elimination`
  data; assert legacy match/round IDs and results survive, started matches keep
  `BEST_OF`, two different groups may both have round 1, and duplicate legacy
  ungrouped rounds remain rejected. Restore the latest migration in cleanup.
- [x] **Run red:** `TURNSTILE_SECRET_KEY=competition-test-key uv run python
  manage.py test competitions.tests.test_round_robin_commands
  competitions.tests.test_migrations competitions.tests.test_models --keepdb`.
- [x] **Implement the model additions and guarded draw commands.** Require
  `competitions.change_competition`, validate under the existing division/root
  lock, supersede rather than delete old drafts, and publish with eligibility
  revalidation. Represent rests through absent fixtures, not BYE match outcomes.
- [x] **Run green** with the same test command, existing elimination command
  tests, and `uv run python manage.py makemigrations --check --dry-run`.
- [x] **Commit only Task 2 files** as `feat(competitions): save and publish round robin group draws`.

## Task 3: Shared fixed-game results and group completion

**Files:** modify `server/competitions/commands.py`, `command_support.py`,
`round_robin_commands.py`, `tests/test_commands.py`,
`tests/test_double_elimination_commands.py`, `tests/test_round_robin_commands.py`.

**Interfaces:**

- Extend the existing series/result validation functions in `commands.py` to
  validate the effective mode, including tiebreak round mode overrides. Existing
  `start_match`, `save_match_progress`, `finalize_match`, and length-override
  signatures remain unchanged.
- `group_standings(group: StageGroup) -> dict` returns standings, ordered
  qualifiers, cutoff-tie sets, and `PROVISIONAL`/`AWAITING_RESOLUTION`/`RESOLVED`
  qualification state. Reads final ordinary matches plus applicable confirmed
  tie decisions; no database write or persisted standings cache.
- `update_round_robin_completion(draw: StageDraw) -> None` is called inside
  mutation transactions. Derive ready/in-progress/awaiting/complete from all
  required fixtures and group cutoffs, rather than an arbitrary last match.

- [x] **Write failing lifecycle tests.** `test_fixed_games_progress_and_draw`
  accepts 1–0 progress for fixed two games, rejects a total of two as progress,
  accepts final 1–1 with `winner=None`, and rejects finals totaling less/more
  than two. Reject negative and noninteger scores rather than allowing database
  conversion to reinterpret them. `test_even_fixed_length_override_and_started_mode_lock` accepts
  length 2 for fixed mode while elimination and decisive tiebreaks reject it.
- [x] **Test group completion.** Finalizing one last-numbered match cannot
  complete a group with earlier pending fixtures. A cutoff tie yields AWAITING;
  a tie wholly among qualified/nonqualified entrants does not block completion.
  Live scores cannot change standings. Ordinary group completion does not emit
  an exceptional no-champion outcome for a multi-group stage.
- [x] **Run red:** focused round robin command tests plus existing result tests.
- [x] **Implement validation and completion at the shared owners.** Freeze mode
  and length on start/progress/finalization; keep score bounds, permissions,
  transactions, repeat-finalization rejection, and elimination routing intact.
- [x] **Run green:** `TURNSTILE_SECRET_KEY=competition-test-key uv run python
  manage.py test competitions.tests.test_commands
  competitions.tests.test_double_elimination_commands
  competitions.tests.test_round_robin_commands --keepdb`.
- [x] **Commit only Task 3 files** as `feat(competitions): support fixed-game draws and group completion`.

## Task 4: Qualification ties and correction impact

**Files:** modify `server/competitions/round_robin_commands.py`, `commands.py`,
`round_robin.py`, `tests/test_concurrency.py`; create
`tests/test_round_robin_ties.py`.

**Interfaces:**

- `preview_group_tie(*, actor, group_id: int, expected_revision: int,
  tied_entry_ids: Sequence[int], method: str,
  ordered_entry_ids: Sequence[int] = (), series_length: int = 1,
  parent_resolution_id: int | None = None) -> dict` returns a signed token,
  current tied set/places, and selected ordering or extra fixtures. No writes.
- `confirm_group_tie(*, actor, token: str, internal_reason: str = "")
  -> TieResolution` revalidates the signed fingerprint/revision and persists
  the reviewed decision or fixtures atomically. Require a nonblank internal
  reason for MANUAL. Manual ordering is a permutation of the exact tied set;
  neither an untied entrant nor extra qualifying places can be introduced.
- Extra rounds reference their resolution, use direct entries, decisive mode,
  and a saved odd series length (default 1). Allocate noncolliding TIEBREAK round
  numbers within the group. Reuse ordinary match scheduling and result commands.
- `project_group_correction(match: Match, *, outcome: str,
  side_one_score: int | None, side_two_score: int | None,
  winner_entry_id: int | None) -> dict` returns before/after standings and
  qualifiers, superseded resolution IDs, and historical-match snapshots.
- `apply_group_correction_impact(match: Match, impact: dict) -> None` applies
  precisely the revalidated projection inside the existing correction transaction.
  Add `group_impact` to the shared signed payload/review response, null outside
  round robin. Do not infer ranking changes from winner changes alone.

- [x] **Write failing tie tests.** Resolve a two-way cutoff tie manually with
  a private reason and through a decisive extra match; resolve a three-way tie
  through three extra matches. Assert original group points never change and a
  remaining relevant tie requires an explicit nested resolution. Reject an
  a parent with unfinished extra matches, wrong subset, duplicate order,
  cross-group IDs, excessive places, stale token, even tiebreak length, tie choice
  before ordinary group play finishes, and a duplicate active choice for the same
  cutoff. Reject generation when total extra contests in the draw, including
  retained superseded contests, would exceed 16,384; a manual decision remains
  available at that limit.
- [x] **Write failing correction tests.** `test_same_winner_score_correction_invalidates_tie`
  changes game difference while retaining the winner; preview includes affected
  decisions and extra results. A changed tied set/source ranking supersedes its
  decision and dependent resolutions, reopens qualification, and keeps unrelated
  regular results. A correction that leaves ranking inputs valid preserves the
  decision with recorded revalidation. Superseded tie matches reject mutation.
- [x] **Add PostgreSQL races.** Concurrent tie confirmations, result-versus-tie
  confirmation, and stale correction previews produce one coherent revision;
  injected history-write failure rolls back scores, decisions, and stage status.
- [x] **Run red:** `TURNSTILE_SECRET_KEY=competition-test-key uv run python
  manage.py test competitions.tests.test_round_robin_ties
  competitions.tests.test_concurrency --keepdb`.
- [x] **Implement preview/confirmation and correction integration.** Fingerprint
  canonical ranking inputs, cutoff, contender identities, and relevant parent
  contests. Preserve superseded records; expose their results as history and
  require a new explicit choice to generate replacement contests. Tie mutations
  use `change_competition`; correction retains both existing change permissions.
- [x] **Run green:** the same command plus existing correction command tests.
- [x] **Commit only Task 4 files** as `feat(competitions): resolve group qualification ties with safe correction`.

## Task 5: Published group, standing, and history contracts

**Files:** modify `server/competitions/serializers.py`, `views.py`, `command_support.py`,
`tests/test_api.py`, `web/src/lib/api/types.ts`,
`web/src/lib/api/competitions.test.ts`, `web/src/routes/bracket-page.test.ts`.

**Interfaces:**

- Keep existing competition/stage/round/match/Changes URLs and revision checks.
  Add `groups` and `round_robin_rules` to stage snapshots; elimination uses `[]`
  and `null`. Rules contain meetings, Decimal point strings, and criterion IDs.
- A group contains `id`, `number`, `name`, `qualifying_places`, `entries`,
  `round_ids`, `standings`, `qualifiers`, `qualification_state`, and
  `tie_resolutions`. Standing rows contain public entry, rank, played/wins/draws/
  losses, point string, games won, game difference, and qualification label
  `PROVISIONAL`/`TIED`/`QUALIFIED`/`NOT_QUALIFIED`.
- Round responses add `group_id`, `tie_resolution_id`, `effective_series_mode`,
  and `resting_entry` (public entry or null). Match responses add
  `effective_series_mode`; set existing `historical` for superseded tie contests.
  Extend immutable result snapshots and their allowlist/TS type with
  `applied_series_mode`, so historical fixed-game draws retain their meaning.
- Tie responses allow only `id`, `parent_id`, `method`, `state`, tied public
  entries, places, ordered public entries, and associated round IDs. Retained
  published superseded tie rounds remain readable as history, excluded from
  current standings. Draft resolutions and private notes never enter snapshots.
- Public Changes adds reviewed tie selection/order and correction qualification
  changes, with previous extra-match snapshots. Explicitly extend the existing
  field allowlist; never serialize a private impact/decision dictionary wholesale.

- [x] **Write failing API tests.** Assert exact fields, Decimal strings, computed
  rankings after fixed draws/forfeits, published-only visibility, unchanged
  snapshot reads/revisions, and consistent group/round/match revision envelopes.
  Manual reasons, actors, contender registration IDs, and private snapshots must
  be absent even from nested Changes and historical extra-match responses.
- [x] **Update typed loader/client fixtures.** Add the new fields to elimination
  fixtures as well as round robin snapshots, and verify the existing stale-revision
  retry/error flow. Do not introduce a second standings API/client cache.
- [x] **Run red:** focused backend API tests and existing client/loader Vitest.
- [x] **Implement the additive allowlists, bounded prefetches, and TS types.**
  Build standings inside `consistent_public_read`; avoid per-standing-row queries.
- [x] **Run green:** `TURNSTILE_SECRET_KEY=competition-test-key uv run python
  manage.py test competitions.tests.test_api --keepdb`; from `web/`,
  `pnpm test:unit --run src/lib/api/competitions.test.ts src/routes/bracket-page.test.ts`.
- [x] **Commit only Task 5 files** as `feat(competitions): expose published groups standings and tie history`.

## Task 6: Organizer group operation in the existing workspace

**Files:** modify `server/competitions/forms.py`, `admin.py`,
`admin_workspace.py`, `templates/admin/competitions/{workspace,action_form,match_detail}.html`,
`static/competitions/{forms.js,workspace.css}`, `tests/test_admin.py`,
`tests/test_workspace.py`; create
`templates/admin/competitions/group_assignment.html` and
`templates/admin/competitions/group_standings.html`.

**Interfaces:**

- Extend setup to ROUND_ROBIN, mode, meetings, points, and ordered criteria.
  Extend draw operation to group names/place counts, manual assignments or
  seeded snake allocation, and an explicitly saved random seed ordering.
- Add group selection and a Standings tab to the same workspace. Existing
  elimination tabs/connector rendering retain their behavior. Group match lists
  show round schedules/rests and effective mode/length, using existing match cards.
- Add guarded `CompetitionAdmin.group_tie_preview_view` and
  `group_tie_confirm_view` URLs/actions consuming Task 4 tokens. Use revision,
  CSRF, organizer permissions, explicit confirmation, and validation feedback.
- Extend result/series forms and match detail to fixed-game limits and draws.
  Present correction standing/qualifier impacts and extra-contest history.
  Generated groups/resolutions remain command-owned, with no generic editable
  model admin or new permission category.

- [x] **Write failing admin/workspace tests.** Exercise setup → approved entrants
  → unequal manual groups/snake → saved preview → publish → fixed-two-games draw
  → standings → manual and extra-match tie confirmation → correction. Assert
  stale forms, tampered token/group ID, missing permissions, non-organizer staff,
  inactive users, and CSRF failures cannot mutate state; GET leaves revision stable.
- [x] **Test effective-mode copy and bounds.** Fixed games permits final 1–1 and
  length 2; a decisive tiebreak identifies best-of and rejects both. The organizer
  can see private reasons in Changes; public-facing links use only display data.
- [x] **Test the ordered rule controls.** Defaults save
  `[HEAD_TO_HEAD, GAME_DIFFERENCE, GAMES_WON]`; selecting Match wins first and
  Head-to-head points fourth saves `[MATCH_WINS, HEAD_TO_HEAD]` when intermediate
  slots are unused. Repeated Head-to-head points fails without changing revision;
  four No rule selections save `[]`. Unknown criteria and rule edits after
  publication fail even through a direct POST. Preview/public copy matches the
  saved order and points exactly.
- [x] **Run red:** `TURNSTILE_SECRET_KEY=competition-test-key uv run python
  manage.py test competitions.tests.test_admin competitions.tests.test_workspace --keepdb`.
- [x] **Implement by extending current forms/workspace patterns.** Use ordinary
  server POST forms and progressive enhancement; keep assignment/standings
  templates focused and preserve full functionality without JavaScript.
- [x] **Run green:** the same command, including current elimination workspace tests.
- [x] **Commit only Task 6 files** as `feat(competitions): operate round robin groups and ties in admin`.

## Task 7: Public group standings, rounds, and qualification states

**Files:** modify `web/src/routes/tournaments/[slug]/games/[gameId]/bracket/+page.svelte`,
`web/messages/en.json`, `web/messages/vi.json`,
`web/src/routes/bracket-page.svelte.spec.ts`.

**Interfaces:**

- Render a ROUND_ROBIN branch of the existing bracket route using Task 5 page data.
  Keep the shared header, normal refresh, existing match IDs, schedule formatting,
  and Changes. No stage handoff controls or speculative stage-navigation shell.
- Use accessible group selection, semantic standings tables, published rule
  descriptions, per-group round lists, rests, draw labels, fixed-game/best-of copy,
  and provisional/awaiting/resolved qualification states in both languages.
- Render ties and recorded resolution selections without presenting tied seed
  order as rank. Superseded extra contests are clearly historical. Group completion
  has group-specific copy instead of the elimination champion-only summary.

- [x] **Write failing Svelte tests.** Assert unequal groups, Decimal points, equal
  ranks, a fixed 1–1 draw, odd-group rest, a boundary tie, manual selection, extra
  contests, historical reset results, and refreshed qualifier changes. Keep the
  current single/double elimination component cases passing.
- [x] **Run red:** from `web/`,
  `pnpm test:unit --run src/routes/bracket-page.svelte.spec.ts`.
- [x] **Implement with existing shadcn-svelte components and Paraglide messages.**
  Contain table/round horizontal scrolling locally; preserve the current visual
  system, semantic labels, keyboard focus, and normal loader error/missing states.
- [x] **Run green:** the same suite, `pnpm check`, and Prettier/ESLint on changed files.
- [x] **Commit only Task 7 files** as `feat(web): display group standings rounds and qualification ties`.

## Task 8: Fixtures, assembled workflow proof, and operating notes

**Files:** modify `server/registrations/dev_seed.py`,
`registrations/tests/test_seed_dev_data_command.py`, `server/e2e/serve.py`,
`web/e2e/django/admin-bracket.spec.ts`, `web/e2e/django/bracket.spec.ts`,
`docs/BRACKET-TODO.md`, `docs/TODO.md`; create
`docs/testing/competition-round-robin.md`.

**Interfaces:**

- Add a published synthetic round robin tournament through commands: one division
  with two unequal groups (3/5 entrants), single meetings and fixed two games;
  another with two four-entry groups, double meetings and best-of three.
  Include ready/live/completed examples, one cutoff tie, manual and extra-match
  history, scheduling, and length overrides. Use fictional snapshots only.
- Seed reruns preserve existing published IDs/results, superseded tie history,
  and unrelated fixtures. The workbook is neither read nor needed at runtime.
- Extend the disposable real-Django browser harness through commands. Keep its
  existing isolated database lifecycle; do not run against a production database.

- [x] **Write failing seed/browser tests.** Verify both schedules independently
  of series length and rerun preservation. Run an organizer journey through full
  publication, fixed-game results, tie choice/confirmation, extra contests, and
  correction; public refresh must show changed standings and retained history.
- [x] **Implement fixtures and notes.** Document setup, odd rests, decimal points,
  ranking criteria, unresolved cutoffs, tie options, correction, and the explicit
  stage-handoff limit. Document migration from populated `0002` and matching
  application/database rollback: old code cannot safely operate round robin data;
  prefer forward fixes once these formats are published.
- [x] **Run focused backend proof:** from `server/`,
  `TURNSTILE_SECRET_KEY=competition-test-key uv run python manage.py test
  competitions registrations.tests.test_seed_dev_data_command --keepdb`,
  `uv run python manage.py makemigrations --check --dry-run`,
  `uv run python manage.py check`, and Ruff on changed Python files.
  PostgreSQL is required for lock/race evidence; report any unavailable checks.
- [x] **Run focused frontend and real browser proof:** from `web/`,
  `pnpm check`, `pnpm test:unit --run src/lib/api/competitions.test.ts
  src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts`,
  `pnpm exec playwright test --config playwright.django.config.ts
  e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts`, and `pnpm build`.
  Cover EN/VI, keyboard group/refresh navigation, and 390px viewport with
  `document.documentElement.scrollWidth <= window.innerWidth`; assert local scroll
  remains usable. Include the existing registration browser journey if shared
  fixtures/harness are changed. Run `git diff --check`.
- [x] **Record actual results and update completion precisely.** Mark G1/G2 only
  after assembled proof. H2/A6/A7/P3 remain partly open for Swiss/handoffs; V1–V5
  remain open for their later-format/cross-stage scope. Record unrun checks and
  environment blockers rather than treating SQLite/mocked tests as PostgreSQL or
  full browser evidence.
- [x] **Commit only Task 8 files** as `test(competitions): verify round robin organizer and public workflows`.

## Plan self-review and execution handoff

Before execution, review the selected scope and interfaces above. The underlying
rules are already approved in the core design; this plan adds their round robin
implementation contracts without reopening the defaults.

Self-review covers exact circle meeting counts, rests, points/game metrics,
head-to-head refinement, frozen modes/lengths, publication locks, manual/extra tie
paths and nested ties, score-only correction impacts, migration row preservation,
public allowlists/history, permissions/concurrency, realistic fixtures, and
responsive EN/VI admin/public workflows. Stage handoffs and Swiss remain explicit
omissions, so their backlog items are not claimed complete.

Review this written plan before implementation, then choose an execution method:
native execution in this session, or subagent-driven task execution. Native is
recommended for this slice because the shared lifecycle, corrections, and snapshot
contracts have substantial sequential dependencies. Independent organizer/public
work can be delegated after those contracts are fixed if subagents are preferred.
