# Swiss Qualification Stages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended here) or superpowers:subagent-driven-development, according to the user's execution choice, to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run fixed-round and threshold Swiss as first or intermediate qualification stages, with saved fair pairings, explicit publication, and safe corrections and handoffs.

**Architecture:** Extend the existing Stage, StageDraw, Round, qualification, and handoff commands. Keep Swiss calculation and matching in one pure module; its command module owns persisted rounds, while shared commands retain result, publication, and correction transactions. Round versions retain history without duplicating the competition or tie-resolution systems.

**Tech Stack:** Python 3.12+, Django 6, PostgreSQL, Django Unfold, NetworkX general graph matching, Svelte 5/SvelteKit, existing UI components, Paraglide EN/VI, Django tests, Vitest, Playwright.

**Spec:** [Approved Swiss design](../specs/2026-10-10-swiss-stages-design.md), approved 2026-10-10. Read it alongside the [delivered multi-stage design](../specs/2026-10-09-multi-stage-competition-design.md).

**Status:** Ready for plan review. No implementation or execution method approved.

## Global Constraints

- Swiss must have a successor: first/intermediate and consecutive Swiss are allowed; standalone/final Swiss and a Swiss champion are prohibited.
- Retain 2–256 entrants, 64 Swiss rounds, and 16,384 ordinary matches per draw. Let `cap = min(64, N - 1 if N % 2 == 0 else N)`; require `1 <= R <= cap` or positive integer `W, L` with `W + L - 1 <= cap`. Reject booleans as integers.
- Prefill `ceil(log2(N))`; do not add a recommended-plus-two cap. Save automatic versus custom policy before first competition publication and resolve automatic counts with each draw's actual field.
- Lock the entire stage plan before the first public fixtures: formats/order, round policies/targets, points/tiebreaks, quotas, group count/order and allocation policy. Preserve established before-play scheduling and series controls.
- Fixed Swiss defaults to 3/1/0 points and `OPPONENT_POINTS` → `GAME_DIFFERENCE` → `GAMES_WON`, with optional `MATCH_WINS`; Top-N is 2 through N. Complete all ordinary rounds and cutoff decisions before handoff.
- Threshold Swiss requires decisive best-of matches; all W-qualified entrants advance, L losses eliminates, and a bye is a normal win. Double forfeits give both entrants a loss and zero points; no fabricated games/opponents.
- Saved stage starting seeds order folding groups. Each Swiss stage resets points, records, byes, opponents and threshold status; prior-stage opponents are allowed. Later seeds use the existing saved random handoff.
- Use whole-round matching. No partial rounds, self-pairs, duplicated/ineligible entrants, silent rematches, or production exhaustive search. Recorded, confirmed rematch exceptions apply only after a complete no-rematch solution fails.
- Save one private next-round preview and explicitly publish it. GET/refresh never regenerates. Corrections supersede later rounds, preserve their played results, and revalidate cutoff resolutions and downstream draws atomically.
- Later entrants are exactly the predecessor's eligible qualifiers. Unknown incoming count is not an assumed half-field or a zero. Never trim qualifiers or alter locked settings to make a handoff fit.
- Preserve organizer authorization, CSRF, division/competition locks, revision checks, signed correction impact and reset consent. Private rounds, fingerprints, actor identities and internal reasons never enter public responses or Changes.
- Preserve all existing format behavior and IDs through migration. No withdrawal/disqualification UI, exceptional chain-ending commands, direct later-stage invitations, provider/realtime work, or registration/payment changes.

## Review Focus

1. A draft next round inside a published draw must remain private, including its bye credit and direct match URL; formerly published superseded matches remain historical (Tasks 4, 8).
2. Correcting an earlier result after later Swiss and successor play must retire every affected round/draw without deleting results or accepting stale consent (Task 6).
3. An unexpectedly small threshold-qualified field must block incompatible custom rounds/targets/quotas, while automatic formulas/group sizes resolve without changing locked rules (Tasks 3, 5).
4. A greedy dead end or unavailable low-bye entrant must not cause a needless rematch, partial round, or unfair repeat bye when a complete legal alternative exists (Task 2).
5. Adding round publication state must preserve public legacy fixtures and private legacy drafts, including published extra tiebreak contests (Task 1).

---

## File Ownership and Order

| Task | Responsibility | Depends on |
| --- | --- | --- |
| 1 | Round history/schema and populated migration compatibility | Existing 0004 |
| 2 | Pure bounds, standings, whole-round pairing and dependency | Independent |
| 3 | Swiss setup, unknown counts and locked automatic group allocation | 1, 2 |
| 4 | Saved round generation/publication and shared match operations | 1–3 |
| 5 | Qualification, termination and exact successor fields | 3, 4 |
| 6 | Swiss corrections and downstream history | 4, 5 |
| 7 | Organizer setup, previews, standings and exception confirmation | 3–6 |
| 8 | Public allowlists, visibility, historical reads and API contract | 4–6 |
| 9 | Public Swiss rounds/standings and EN/VI presentation | 8 |
| 10 | Synthetic fixtures, PostgreSQL races, browser proof and docs | 7–9 |

New production modules are `server/competitions/swiss.py` (pure calculation),
`swiss_commands.py` (configuration and rounds), and `swiss_corrections.py`
(projection/retirement integrated into existing correction transactions).
Extend `stage_commands.py`, `qualification.py`, and `handoff_commands.py` in
their existing roles. Do not introduce a generic format registry or a second
result/tie system. Shared-file work is sequential; this plan grants no agent
delegation or implementation authorization by itself.

Commands below run from `server/` unless marked `web/` or repository root.
Each task stages only its own changes and commits after its focused proof.

### Task 1: Persist Swiss settings and versioned rounds without changing existing visibility

**Files:** Modify `server/competitions/models.py`, `commands.py`,
`command_support.py`, `qualification.py`, `handoff_commands.py`;
create `server/competitions/migrations/0005_swiss.py`;
extend `server/competitions/tests/test_models.py`, `test_migrations.py`.

**Interfaces:**

- `Stage.swiss_round_count: int | None` (null means automatic for fixed Swiss),
  `swiss_win_target: int | None`, `swiss_loss_limit: int | None`.
  Reuse `advancement_count` for fixed Top-N; threshold has no quota.
- `StageDraw.swiss_round_limit: int | None` stores the resolved ordinary-round
  ceiling; it is immutable for that draw after creation.
- `StageGroupPlan.size: int | None`: all-null group sizes mean the locked
  automatic allocation rule; all concrete sizes mean the existing exact plan.
- `Round.version: int = 1`, `state: DRAFT | PUBLISHED | SUPERSEDED`,
  `published_at: datetime | None`, `source_fingerprint: str = ""`,
  `rematches_authorized: bool = False`. Default state is DRAFT; the first
  publication timestamp is never cleared. Reasons stay in private Changes.

- [ ] **Write populated migration tests.** Migrate from 0004 with draft,
  published and superseded draws, normal rounds, current/superseded extra
  contests, scores, source entries and stored codes. Assert IDs, slots, results,
  lineage, labels, quota values and public/private visibility are preserved.

```python
# test_round_migration_preserves_legacy_publication (historical models)
self.assertEqual(new_match.pk, old_match_id)
self.assertEqual((new_match.side_one_score, new_match.winner_id), (2, winner_id))
self.assertEqual(published_round.state, "PUBLISHED")
self.assertIsNotNone(published_round.published_at)
self.assertEqual(draft_round.state, "DRAFT")
self.assertIsNone(draft_round.published_at)
self.assertEqual(retired_public_round.state, "SUPERSEDED")
self.assertIsNotNone(retired_public_round.published_at)
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_models competitions.tests.test_migrations --noinput`.** Expect missing-field/migration failures.
- [ ] **Add fields and constraints.** Permit fixed Swiss advancement and null
  automatic group sizes; retain positive targets, quotas and size bounds.
  Replace each group/no-group round uniqueness constraint with versioned
  uniqueness plus one non-superseded version per existing logical round key.
  Require positive versions and published rounds to have a timestamp; draft
  rounds must have none. Superseded rounds may be formerly public or private.
  Allow incomplete legacy Swiss placeholders to stay private; do not invent
  targets or quotas during migration. Publication validation rejects them.
- [ ] **Backfill publication and wire existing writers.** Derive legacy state
  from draw publication/supersession and tie supersession. Use the draw's known
  publication timestamp as legacy visibility evidence, not an invented exact
  tie publication time. `publish_draw` publishes its current draft rounds in
  the same transaction; committed extra-contest creation in a public draw
  marks those rounds published. Tie/draw retirement marks their rounds
  superseded. Preserve existing automatic-result behavior for non-Swiss draws.
- [ ] **Run the two focused modules plus `competitions.tests.test_api`,
  `competitions.tests.test_qualification` and `makemigrations --check --dry-run`.**
  Expect PASS and no model drift. Assert duplicate current versions fail at DB
  level while a replacement can coexist with retained superseded versions.
- [ ] **Commit:** `feat(competitions): persist Swiss settings and round history`.

### Task 2: Calculate standings and complete deterministic Swiss pairings

**Files:** Create `server/competitions/swiss.py`,
`server/competitions/tests/test_swiss.py`; modify `server/pyproject.toml`,
`server/uv.lock` for the verified matching dependency.

**Interfaces in `swiss.py`:**

- `resolve_round_limit(entrant_count: int, *, format: str, round_count: int | None, win_target: int | None, loss_limit: int | None) -> int`.
- `SwissResult`: immutable record of `match_id`, `round_number`,
  `side_one_id`, optional `side_two_id` (bye), `outcome`, optional scores and
  `winner_id`. These are StageEntry IDs; entries/seeds are supplied separately.
- `SwissStanding`: entry ID, rank, played, wins, draws, losses, Decimal points,
  games won/difference, Decimal opponent points, bye count, and
  `status: ACTIVE | QUALIFIED | ELIMINATED` (threshold exit state).
- `rank_swiss(entry_seeds: Mapping[int, int], results: Sequence[SwissResult], *, format: str, points: tuple[Decimal, Decimal, Decimal], tiebreaks: Sequence[str], win_target: int | None = None, loss_limit: int | None = None) -> list[SwissStanding]`.
- `pair_swiss_round(entry_seeds: Mapping[int, int], standings: Sequence[SwissStanding], results: Sequence[SwissResult], *, format: str, allow_rematches: bool = False) -> SwissPairing`.
  `SwissPairing` holds canonical `pairs: tuple[tuple[int, int], ...]`,
  `bye_entry_id: int | None`, `repeat_pairs`, and `cross_group_pairs`.
  Raise `SwissPairingError(ValueError)` for incomplete/ineligible inputs or
  infeasibility; commands convert it to existing user-facing ValidationError.

- [ ] **Write named pure tests for exact setup limits and standings.** Cover
  N=2/3/8/9/256, custom/automatic counts, booleans, W/L sum bounds, tied ranks
  without seed qualification, fixed-game draws, repeated opponents, byes and
  double forfeits. A normal bye adds one win and win points, no opponent or
  games; count it as one assigned round in `played`, with separate `bye_count`.
  Forfeit opponents contribute current points; each meeting contributes once.

```python
# test_round_limits_and_saved_seed_folding
self.assertEqual(resolve_round_limit(9, format="SWISS_FIXED",
    round_count=None, win_target=None, loss_limit=None), 4)
self.assertEqual(pairing.pairs, ((1, 8), (2, 7), (3, 6), (4, 5)))
# test_double_forfeit_and_qualifying_bye
# This entrant already has two forfeit wins and no played games.
self.assertEqual((bye.wins, bye.games_won, bye.bye_count), (3, 0, 1))
self.assertEqual(bye.status, "QUALIFIED")
self.assertEqual((left.losses, right.losses, left.points, right.points), (1, 1, 0, 0))
```

- [ ] **Add adversarial matching fixtures.** With four active vertices and
  allowed edges `{(1,2), (1,3), (2,4)}`, require `{(1,3), (2,4)}` rather than
  greedy `(1,2)`. Test adjacent/distant group moves, forfeit opponent history,
  one active entrant receiving a bye, odd first-round last-seed bye, and a
  low-bye candidate who strands others while another permits full coverage.
  Assert no-repeat failure without override, and minimum necessary repeats
  with it. Tiny exhaustive reference matchings verify coverage and the entire
  preference order; exhaustive search stays only in tests.
- [ ] **Run `uv run python manage.py test competitions.tests.test_swiss --noinput`.** Expect missing-module failures.
- [ ] **Verify and lock NetworkX.** Stable documentation inspected during
  planning was 3.7. Confirm Python compatibility, package metadata and license
  during installation, then pin the verified compatible release and commit the
  uv lock. Use [`min_weight_matching`](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.matching.min_weight_matching.html): it returns minimum-cost maximum-cardinality
  matching, so explicitly check full coverage, including an odd-field dummy.
  Integer costs avoid floating-point ambiguity. This dependency supplies a
  maintained polynomial general-graph solver; do not implement blossom locally.
- [ ] **Implement calculations and matching.** Compute opponent totals after
  all base points; validate one appearance per entry per result round. Fixed
  score groups use points; threshold groups use W/L and exclude exited entries.
  Group order is points descending or wins descending/losses ascending;
  within-group order always uses saved seeds. Run with previous-opponent edges
  absent first, even when override is requested. Establish feasible bye choices
  under the approved count → lowest score/record → worst seed policy. Among
  solutions respecting that bye policy, minimize repeat pairs (override only),
  cross-group pairs, point/record distance, then folding deviations. Treat bye
  fairness as a constraint, not permission to silently add rematches.
- [ ] **Encode and prove bounded preferences.** Fixed distance is scaled Decimal
  point distance; threshold distance is `abs(w1-w2) + abs(l1-l2)`. Folding cost
  is distance from opposite positions in seed order within a group (or the
  two groups' merged seed order for a cross-group pair). Derive integer
  multipliers from maximum lower-priority totals, never magic large weights.
  Stable seed-based node/edge insertion and canonical output settle equal
  choices under the locked solver version. Do not use database IDs for priority.
- [ ] **Run pure tests and different-hash-seed subprocess fixtures.** Assert
  identical pairs for hash seeds 1/7/73 and input-order permutations. Measure
  representative/adversarial 256-entry rounds with the pinned solver; record
  runtime in final proof rather than adding fragile wall-clock assertions.
- [ ] **Commit:** `feat(competitions): calculate Swiss standings and pairings`.

### Task 3: Configure Swiss and validate known or outcome-dependent stage fields

**Files:** Create `server/competitions/swiss_commands.py`; modify
`server/competitions/stage_commands.py`, `command_support.py`;
create `server/competitions/tests/test_swiss_plan.py`; extend `test_stage_plan.py`.

**Interfaces:**

- `configure_swiss(*, actor, competition_id: int, expected_revision: int, stage_sequence: int = 1, name: str, format: str, series_mode: str, default_series_length: int, round_count: int | None, win_target: int | None, loss_limit: int | None, advancement_count: int | None, win_points: Decimal, draw_points: Decimal, loss_points: Decimal, tiebreaks: Sequence[str]) -> Stage`.
- Extend `validate_stage_plan(competition) -> list[dict]`: existing
  `incoming_count`/`ordinary_match_count` may be null pending actual-field
  validation; `outgoing_count` is null for threshold or final stages. Preserve
  stage IDs and order. Add `requires_actual_field_validation: bool`; infer why
  a count is unknown from the stage format, not a separate state machine.
- `resolve_group_sizes(group_specs: Sequence[tuple[str, int | None, int]], incoming_count: int) -> list[int]` in `stage_commands.py`.
  Extend `set_stage_groups` to accept that shape (name, optional size, quota).
  Existing callers with concrete sizes remain compatible.

- [ ] **Write plan tests.** Accept Swiss→SE, SE→Swiss→SE, three Swiss stages→SE,
  and mixed consecutive presets. Reject final/standalone Swiss at validation,
  first publication, reorder/removal validation and direct command boundaries;
  allow a private incomplete chain to be configured. Verify round, target,
  series, point/tiebreak and quota validation before persistence.
- [ ] **Write unknown-count and locking assertions.** Threshold makes the next
  incoming count unknown; RR, elimination and fixed-Swiss quotas restore known
  outgoing counts. Test longer chains returning to unknown again. Reconfiguration
  after first publication fails without revision or data changes. Do not reject
  all unknown fields as undersized and do not promise compatibility in advance.

```python
# test_locked_automatic_group_sizes
groups = [("A", None, 2), ("B", None, 2)]
self.assertEqual(resolve_group_sizes(groups, 7), [4, 3])
self.assertEqual(resolve_group_sizes(groups, 8), [4, 4])
self.assertEqual(resolve_group_sizes(groups, 9), [5, 4])
self.assertEqual(resolve_group_sizes([("A", None, 4), ("B", None, 1)], 7), [4, 3])
with self.assertRaises(ValidationError):
    resolve_group_sizes(groups, 3)
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_swiss_plan competitions.tests.test_stage_plan --noinput`.** Expect validation failures.
- [ ] **Implement configuration in existing lock/revision boundaries.** Store
  null round count for automatic fixed mode even when the UI displays its
  current recommendation. Clear inapplicable Swiss fields on unlocked format
  changes. Threshold forces best-of and no Top-N; fixed accepts existing valid
  result modes and only the approved Swiss tiebreaks. Configuration invalidates
  affected drafts through existing helpers, not live histories.
- [ ] **Extend full-chain validation and allocation.** Validate known counts
  immediately. For unknown counts validate structure, positive integer targets,
  the 64-round absolute limit and quotas against the 256-entry support ceiling;
  defer field-dependent feasibility/budget checks explicitly. At a concrete
  field resolve all limits and ordinary-match estimates before persistence.
  Exact group plans require sizes to sum to N; automatic plans reserve
  `max(2, quota)` then fill the smallest group, breaking ties by saved order.
  Reject mixed exact/automatic groups. Resolving sizes never mutates group plans.
- [ ] **Run both test modules; expect PASS.** Include bad quota/field cases,
  oversized match estimates, custom counts surviving entrant-count edits,
  and direct attempts to edit a future stage after publication.
- [ ] **Commit:** `feat(competitions): validate Swiss stage plans and variable fields`.

### Task 4: Generate, save and publish one current Swiss round

**Files:** Extend `server/competitions/swiss_commands.py`; modify
`server/competitions/command_support.py`, `commands.py`;
create `server/competitions/tests/test_swiss_commands.py`.

**Interfaces in `swiss_commands.py`:**

- `save_swiss_draw(*, actor, competition_id: int, expected_revision: int, ordered_entrant_ids: Sequence[int] | None = None, randomized: bool = False, stage_id: int | None = None) -> StageDraw`: first-stage saved seeds; later stages use handoff commands.
- `swiss_standings(draw: StageDraw, *, projected_matches: Sequence[Match] | None = None) -> list[SwissStanding]`: uses only current published ordinary rounds and confirmed results, scoped to this draw.
- `_persist_swiss_round(draw: StageDraw, *, number: int, pairing: SwissPairing, source_fingerprint: str, rematches_authorized: bool) -> Round`: called only under the owning transaction; creates a new version and two slots per match, including an empty bye slot.
- `generate_swiss_round(*, actor, stage_id: int, expected_revision: int, regenerate: bool = False, allow_rematches: bool = False, internal_reason: str = "") -> Round`.
- `publish_swiss_round(*, actor, round_id: int, expected_revision: int) -> Round`.

- [ ] **Write saved-round lifecycle tests.** Draw creation saves only round 1;
  initial publication publishes that round. Next-round generation requires all
  prior current ordinary matches final and a continuing stage. Repeated generate
  returns the valid saved draft; refresh does not invoke solver/randomization.
  Explicit regeneration supersedes the draft, increments version and keeps IDs.
  Pending/final private bye fixtures contribute no public/current standings.

```python
# test_draft_bye_has_no_current_credit_and_cannot_be_played
self.assertEqual(before_points, points_from(swiss_standings(draw)))
with self.assertRaises(ValidationError):
    start_match(actor=organizer, match_id=draft_match.pk,
                expected_revision=competition.revision)
# After explicit publication, a saved bye contributes exactly once.
self.assertEqual(after_bye.wins, before_bye.wins + 1)
```

- [ ] **Write source and override tests.** Reject stale revisions/fingerprints,
  unapproved registrations, duplicate/foreign entries, incomplete coverage and
  custom/rematch payload tampering at publication. A no-rematch dead end creates
  no partial rows/change; override requires explicit POST intent and nonblank
  reason. A feasible no-rematch round remains repeat-free even with the flag.
- [ ] **Run `uv run python manage.py test competitions.tests.test_swiss_commands --noinput`.** Expect missing-command or lifecycle assertion failures.
- [ ] **Integrate draw dispatch and source fingerprints.** `_persist_stage_draw`
  resolves/stores the Swiss limit and dispatches Swiss explicitly. Hash saved
  rules/limit, seeds/eligibility and prior current result inputs (outcomes,
  slots, configured score metrics) in canonical order; scheduling is excluded.
  Persist pairings and audit reason privately; no public Change at generation.
  A draw's round codes append after every retained match in that draw, including
  superseded versions, using existing `{stage.name}-M{ordinal}` convention.
  Enforce the ordinary-match storage budget before every new batch, including
  retained superseded ordinary matches; keep the existing extra-contest budget.
- [ ] **Wire publication and shared match guards.** Recheck actual-field limits,
  full coverage, no repeats unless authorized, source and eligibility under
  existing locks. Publish the saved round, resolve its bye and record public
  Changes atomically. `_validate_saved_draw`, `_ordered_matches`, automatic
  result resolution and `_lock_match` must distinguish current/public rounds.
  Saved-draw validation includes current drafts; result progression/standings
  include only current published rounds, never drafts or superseded versions.
  All scheduling, start/progress/finalize, round/match series and correction
  entrypoints reject private/superseded rounds. Enforce decisive threshold
  overrides at the command boundary, not only the setup form.
- [ ] **Run Swiss command tests plus existing command, round-robin and double-
  elimination command suites.** Expect PASS. Publish one explicit next round;
  finalizing its last match must never generate or publish another automatically.
- [ ] **Commit:** `feat(competitions): save and publish Swiss rounds`.

### Task 5: Resolve Swiss qualification and preserve exact stage handoffs

**Files:** Modify `server/competitions/qualification.py`, `handoff_commands.py`,
`commands.py`, `swiss_commands.py`; create
`server/competitions/tests/test_swiss_handoffs.py`; extend `test_qualification.py`.

**Interfaces:** Extend existing `stage_qualification(draw, *, projected_matches=None)`
without replacing its dictionary contract: `qualification_state`,
`qualifier_entry_ids`, `fingerprint`, `block_reason`, `bands`, `cutoffs`,
`resolution_states`. Add `update_swiss_completion(stage: Stage, draw: StageDraw) -> None`
in `swiss_commands.py`. Reuse `select_qualifiers`, `_source_field`,
`validate_draw_source` and `generate_next_stage_draw` signatures.

- [ ] **Write termination and cutoff tests.** All currently generated matches
  finishing before R must leave fixed Swiss incomplete. At R, a cutoff tie is
  AWAITING_RESOLUTION until the existing manual or extra-match workflow resolves
  it. Extra contests do not alter ordinary points/history or use ordinary-round
  budget. Threshold exits at W/L and completes only when no active entries
  remain; a qualifying bye and double forfeits can change outgoing field size.
- [ ] **Write variable-field and stage-reset assertions.** Exercise a 7/8/9
  actual field into automatic RR groups, zero/one qualifier blocking handoff,
  an automatic Swiss count resolving to 4 at N=9, and a locked custom R=8
  blocking at N=7. Reject incompatible W/L/quota/eligibility without changing
  rules, dropping entrants or saving a partial successor draw.

```python
# test_consecutive_swiss_starts_fresh
self.assertEqual(set(e.source_entry_id for e in next_draw.entries.all()), qualified_ids)
self.assertTrue(all((r.wins, r.losses, r.points, r.bye_count, r.status)
                    == (0, 0, 0, 0, "ACTIVE") for r in swiss_standings(next_draw)))
self.assertIsNone(next_draw.stage.champion_id)
# A prior-stage meeting is allowed; a repeat within next_draw still is not.
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_swiss_handoffs competitions.tests.test_qualification --noinput`.** Expect completion/handoff failures.
- [ ] **Implement format branches in qualification/completion.** Use current
  published ordinary rounds and explicit configured termination, not merely
  absence of pending fixtures. Filter `projected_fixture_matches` by current
  published rounds too, retaining current published tiebreak contests for their
  separate cutoff evaluation. Fixed Swiss reuses draw-scoped cutoff selection
  and tie records; threshold returns all qualified entries after stage completion
  without Top-N trimming. Preserve real tied bands, not seed-based qualification.
  `_update_stage_completion` dispatches Swiss explicitly and never writes a
  champion. Fingerprints include every relevant current input and resolution.
- [ ] **Extend source/destination validation.** `_source_field` takes the actual
  resolved qualified set instead of comparing threshold output to a fictitious
  quota. Preserve registration locks, approval, division, exact membership and
  `source_entry` lineage. Resolve group sizes before the existing saved random
  assignment; persist sizes on `StageGroup`, not locked `StageGroupPlan`. Resolve
  Swiss limits on the new draw and revalidate on publication. Refresh preserves
  that saved assignment/limit; only a replacement draw recomputes them.
- [ ] **Run Swiss handoff, qualification, existing handoff and stage-plan tests.**
  Expect PASS; include RR→Swiss→DE and Swiss→Swiss→Swiss→SE with stage-local
  history/seed assertions and unknown/known-count transitions.
- [ ] **Commit:** `feat(competitions): qualify and advance Swiss entrants`.

### Task 6: Retire later rounds and revalidate successors on corrections

**Files:** Create `server/competitions/swiss_corrections.py`,
`server/competitions/tests/test_swiss_corrections.py`; modify
`server/competitions/commands.py`, `qualification.py`, `handoff_commands.py`;
extend `test_stage_corrections.py`.

**Interfaces:** `project_swiss_correction(draw: StageDraw, *, projected_matches: Sequence[Match]) -> dict`
returns `retired_round_ids`, `retired_match_ids`, `played_match_ids`, and
`current_match_ids`; `apply_swiss_correction(draw: StageDraw, impact: dict) -> None`
marks retirement under the existing owning transaction. The projection compares
current pairing/standings inputs; a scheduling-only or identical-input change
returns empty retirement sets. These functions do not commit or record a
separate revision. Use existing signed correction token/public impact allowlist.

- [ ] **Write `test_earlier_correction_retires_all_later_rounds_and_downstream_play`.**
  Play multiple Swiss rounds and successor matches, preview an earlier winner
  correction, and assert impact includes later draft and published rounds,
  cutoff contests and affected downstream draws. After confirmation their old
  scores, IDs and codes remain; standings use only retained current rounds.
  Assert the current result edit remains auditable via existing snapshots.
- [ ] **Write invalidation/race tests.** A score-only correction affecting a
  configured game tiebreak invalidates later rounds even with the same winner.
  Identical-input/schedule changes do not. Token replay, intervening results and
  missing reset consent must leave all state/history unchanged.

```python
# test_history_is_retained_after_confirmed_correction
later_match.refresh_from_db()
self.assertEqual((later_match.side_one_score, later_match.winner_id), old_result)
self.assertEqual(later_match.round.state, "SUPERSEDED")
self.assertNotIn(later_match.pk, current_match_ids)
self.assertEqual(replacement.number, retired_round.number)
self.assertGreater(replacement.version, retired_round.version)
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_swiss_corrections competitions.tests.test_stage_corrections --noinput`.** Expect retirement assertions to fail.
- [ ] **Project and apply through existing correction boundaries.** Integrate
  into `_project_correction`, signed payload/review and `apply_correction`.
  Exclude retired Swiss results from the existing in-place elimination reset
  list. Supersede all later generated ordinary rounds when inputs change;
  re-evaluate cutoff fingerprints and retire dependent extra contests. Pass the
  projected current set through shared qualification and handoff correction
  projection before applying anything. Preserve unaffected current-round matches.
- [ ] **Revalidate the entire dependent chain atomically.** Reuse handoff impact
  retirement/preservation logic; no downstream draw remains current against
  stale qualifiers or fingerprints. Regeneration begins after the last retained
  completed round; replacement draws resolve formulas/group allocation again
  under locked policies. Keep private retired previews out of public Changes.
- [ ] **Run Swiss correction, stage correction, qualification and handoff suites.**
  Expect PASS, including corrections changing threshold-qualified count and
  corrections that preserve qualified membership but change its fingerprint.
- [ ] **Commit:** `feat(competitions): preserve Swiss correction history`.

### Task 7: Add organizer Swiss setup, previews and round controls

**Files:** Modify `server/competitions/forms.py`, `admin.py`, `admin_workspace.py`,
`server/competitions/templates/admin/competitions/workspace.html`,
`action_form.html`, `group_rules.html`, `match_detail.html`,
`server/competitions/static/competitions/forms.js`, `workspace.css`;
create `server/competitions/templates/admin/competitions/swiss_standings.html`,
`server/competitions/tests/test_swiss_workspace.py`; extend `test_stage_workspace.py`.

**Interfaces:** Extend `CompetitionSetupForm` and existing `_save_setup` routing;
add `SwissRoundForm` (revision), `SwissRematchForm` (revision, explicit confirmation,
internal reason), and stage-scoped generate/publish views calling Task 4 commands.
Build workspace context from persisted round/standings data, not a new solver
call. Reuse common action forms, match cards and correction impact display.

- [ ] **Write organizer tests.** Assert known-N recommendation, unknown-N formula
  copy, custom-value preservation, fixed versus threshold fields, later-stage
  Swiss choices, automatic RR group quotas and locked-plan state. Assert selected
  stage survives redirects and no invalid final Swiss plan can publish.
- [ ] **Write round-control tests.** GET/refresh never mutates/re-pairs. Generate,
  explicit publish and required-rematch confirmation use CSRF POSTs and current
  revision. Preview explains bye/repeated bye/cross-group/rematch choices; stale
  inputs show actionable errors. Reject non-organizers and missing permissions.
  Historical/private rounds expose no normal match-mutation actions.

```python
# test_swiss_preview_refresh_is_read_only (existing organizer client fixture)
self.assertEqual(first_context["round"].pk, refreshed_context["round"].pk)
self.assertEqual(competition.revision, revision_before_get)
self.assertEqual(denied_publish.status_code, 403)
```
- [ ] **Run `uv run python manage.py test competitions.tests.test_swiss_workspace competitions.tests.test_stage_workspace --noinput`.** Expect missing forms/actions.
- [ ] **Extend setup/workspace in the established polished layout.** Label the
  default **Recommended rounds**; display pending `ceil(log2(actual N))` for an
  automatic later stage. Show Top-N only for fixed and W/L only for threshold,
  with server-authoritative errors. Display published versus private preview,
  current round/limit, standings and threshold exits, cutoff actions and handoff
  blocking reasons. Show automatic RR sizes only once the field is known.
- [ ] **Wire exception and correction confirmation.** Only offer **Allow required
  rematches** after no-rematch failure; saved publication uses its recorded
  authorization. Include retired rounds and played downstream impacts in the
  existing confirmation screen. Do not add a free-form per-round pairing editor;
  all saved pairings still receive full server validation at publication.
- [ ] **Run workspace, stage-workspace and admin suites.** Expect PASS; verify
  field labels/help associations, keyboard operation, narrow tables, and no
  solver side effects in rendering. Browser coverage follows in Task 10.
- [ ] **Commit:** `feat(admin): manage Swiss qualification rounds`.

### Task 8: Expose allowlisted Swiss state without leaking round previews

**Files:** Modify `server/competitions/views.py`, `serializers.py`;
create `server/competitions/tests/test_swiss_api.py`; extend
`server/competitions/tests/test_api.py`, `test_stage_api.py`.

**Interfaces / public contract:** Add nullable `swiss_rules` and a `swiss_standings` array to
`PublicStageSerializer` (`swiss_standings=[]` for non-Swiss). Rules expose only
`round_policy: AUTOMATIC | CUSTOM | THRESHOLD`, resolved `round_limit`,
`win_target`, `loss_limit`, `win_points`, `draw_points`, `loss_points` (strings)
and `tiebreaks` (names). Each standing
contains the existing public entry plus rank, played/W/D/L, points, games
won/difference, opponent points, bye count and threshold `status`. Reuse the
existing `qualification` object for cutoff/advancement state; threshold
`advance_count` remains null, with actual resolved qualifiers in its list.

- [ ] **Write the visibility matrix tests.** Exercise competition/stage/round/
  match endpoints and public Changes for public draw + private next round,
  superseded private preview, published current round, superseded public round
  and superseded public draw. Assert private round/match IDs, results, bye credit,
  fingerprints and override reasons never appear. Direct private URLs return
  404; formerly published match detail remains 200 with `historical=true`.

```python
# test_private_swiss_round_is_inaccessible_inside_published_draw
self.assertEqual(private_round_response.status_code, 404)
self.assertEqual(private_match_response.status_code, 404)
self.assertNotIn(private_match.pk, snapshot_match_ids)
self.assertTrue(retired_public_match_response.json()["historical"])
```
- [ ] **Run `uv run python manage.py test competitions.tests.test_swiss_api --noinput`.** Expect visibility/contract assertions to fail.
- [ ] **Filter public rounds at every boundary.** Snapshot prefetches and
  `get_rounds` expose only current published rounds. Direct round reads require
  current published round and draw; preserve the existing historical-match
  detail route using both round and draw publication timestamps. A superseded
  private round inside a published draw is still private. Update historical
  flags, qualification caches and stage-filtered Changes lookup accordingly.
- [ ] **Serialize Swiss rules, standings and Changes explicitly.** Remove the
  non-RR/no-advancement shortcut that hides threshold qualification. Never
  produce a Swiss champion. Generation/override authorization stays private
  until publication. `SWISS_ROUND_PUBLISHED` exposes `stage_id`, `round_id`,
  `round_number`, `match_ids`, `rematch_count` and `repeated_bye`, with no
  actor/reason. Existing correction Changes gain `swiss_impact` containing
  `retired_round_ids` and `retired_match_ids`, filtered to formerly published
  rows. Extend `PublicChangeSerializer`'s allowlist explicitly; existing
  match/result snapshots remain the history payload.
  Preserve repeatable-read snapshots, revision pagination and bounded queries.
- [ ] **Run Swiss API and both existing API suites.** Expect PASS for field
  allowlists, query bounds, old-format responses and public snapshot/Changes
  revision consistency. Include private preview creation between two reads.
- [ ] **Commit:** `feat(api): expose published Swiss rounds and standings`.

### Task 9: Render public Swiss pairings, standings and qualification

**Files:** Modify `web/src/lib/api/types.ts`,
`web/src/routes/tournaments/[slug]/games/[gameId]/bracket/+page.svelte`,
`web/messages/en.json`, `web/messages/vi.json`,
`web/src/routes/bracket-page.test.ts`, `bracket-page.svelte.spec.ts`,
`web/src/lib/api/competitions.test.ts`.

**Interfaces:** Add `PublicCompetitionSwissRules` and
`PublicCompetitionSwissStanding` matching Task 8 exactly, and nullable rules/
standings array to `PublicCompetitionStage`. Keep existing API client/loader,
stage/round IDs, qualification types, sequential public match-label mapping,
refresh flow and historical match links.

- [ ] **Write component assertions.** Fixed Swiss shows selected-round pairings,
  current round/limit, points/opponent points and cutoff state. Threshold shows
  W/L records and active/qualified/eliminated status. Bye labels have no invented
  scores; public rematch Changes display safe explanatory copy. Neither mode
  shows a champion. Stage/round switching resets dependent filters, and removed
  rounds after correction cannot leave an invalid selection.
- [ ] **Run focused Vitest suites from `web/`; expect missing rendering/type failures.**

```typescript
// shows threshold qualification without a champion (existing render fixture)
await expect.element(page.getByText('Qualified', { exact: true }).first()).toBeVisible();
await expect.element(page.getByRole('heading', { name: 'Champion' })).not.toBeInTheDocument();
await expect.element(page.getByRole('link', { name: historicalLabel }))
  .toHaveAttribute('href', historicalHref);
```
- [ ] **Extend the existing public page.** Use the same round selector, match
  cards, qualification display and contained `.cw-bracket-scroll` behavior.
  Add accessible Swiss standings and rules text with EN/VI translations; keep
  the table readable at narrow widths and hide irrelevant format columns.
  Distinguish finished qualification from a champion, and preserve awaiting-
  replacement stages/history. Do not expose internal versions or fingerprints.
- [ ] **Run from `web/`:** `pnpm exec vitest run src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts src/lib/api/competitions.test.ts`,
  then `pnpm check`. Expect PASS and no errors; existing elimination/RR fixtures
  use null Swiss rules and empty Swiss standings. Assert exact historical link
  hrefs and meaningful localized status text, not only snapshots.
- [ ] **Commit:** `feat(web): display Swiss qualification stages`.

### Task 10: Prove complete workflows and document operation

**Files:** Modify `server/registrations/dev_seed.py`,
`server/registrations/tests/test_seed_dev_data_command.py`,
`server/e2e/fixtures.py`, `server/competitions/tests/test_concurrency.py`,
`web/e2e/django/admin-bracket.spec.ts`, `web/e2e/django/bracket.spec.ts`,
`docs/BRACKET-TODO.md`, `docs/testing/competition-multi-stage.md`;
create `docs/testing/competition-swiss.md`.

**Interfaces:** Reuse `seed_development_data`, the existing disposable Django
browser harness and PostgreSQL concurrency-test helpers. No new seed command,
mock backend, personal-data import or persistent test service.

- [ ] **Add failing fixture/race tests.** Seed `dev-usec-swiss` with an odd-field
  division (9 entrants, 4 fixed-two-game rounds, Top-4→SE) and a threshold→
  Swiss→playoffs division (16 entrants, W=3/L=3→automatic fixed Swiss Top-4→SE).
  Reruns preserve published draw/round/match IDs, scores, saved limits, unrelated
  tournaments and payment settings. Race two same-revision generation requests:
  exactly one version/revision/change persists. Race publication against a
  correction/eligibility change and assert one coherent serialized outcome.

```python
# test_concurrent_swiss_generation_saves_one_current_round
self.assertEqual(current_rounds.count(), 1)
self.assertEqual(competition.revision, starting_revision + 1)
self.assertEqual(saved_change_count, 1)
self.assertEqual(preserved_seed_match_ids, original_seed_match_ids)
```
- [ ] **Run seed and concurrency tests on PostgreSQL; expect new fixture assertions to fail.**
- [ ] **Implement synthetic fixtures and browser journeys.** Reuse real guarded
  commands. Cover configure→seed→private preview→publish→result→next round→
  cutoff/threshold completion→saved handoff, plus intermediate/consecutive Swiss.
  Include a repeat exception and earlier correction after downstream play in
  disposable scenarios. Assert organizer and public EN/VI views, mobile scroll,
  bye status, lock errors, current versus historical scores and preview privacy.
- [ ] **Run final backend gates from `server/`:**

```bash
uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command --noinput
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run ruff check competitions e2e registrations/dev_seed.py registrations/tests/test_seed_dev_data_command.py
```

- [ ] **Run final frontend/browser gates from `web/`:**

```bash
pnpm exec vitest run src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts src/lib/api/competitions.test.ts
pnpm check
pnpm build
pnpm exec playwright test --config=playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts
```

- [ ] **Record evidence and operational limits.** Use test-only Turnstile setup
  and `collectstatic` if required by the existing harness; distinguish environment
  blockers from failures. SQLite-only proof cannot establish locking/race safety.
  Record populated migration, solver determinism/runtime and browser evidence.
  Document automatic versus custom rules, unknown fields, blocked pairings,
  rematch consent, bye qualification, correction history and stage-local resets.
  Take a database backup before deployment; after Swiss data exists, reverting
  only code/migration is unsafe—use a forward fix or matching code/database
  backup. No deployment is part of this plan.
- [ ] **Update delivery tracking only after passing proof.** Mark S1–S3 delivered
  and describe Swiss coverage of H2/A6/A7/P3 without closing deferred withdrawal,
  realtime or exceptional-chain work. Record exact checks and limitations in
  the testing guide; do not claim unexecuted checks.
- [ ] **Commit:** `test(competitions): verify Swiss workflows and document operation`.

## Self-review and Execution Handoff

Spec coverage: placement/limits/locking → Tasks 1–3; results/seeds/matching →
Tasks 2/4; qualification and outcome-dependent successors → Tasks 3/5;
publication/corrections → Tasks 4/6/8; organizer/public delivery → Tasks 7–10.
Each Review Focus item has an owning regression above. Application tests and
dependency installation are execution work, not evidence from this planning pass.

Recommend native execution because these tasks share the same transaction,
qualification and visibility boundaries. Implement in order with focused
checks and intent-based commits, followed by independent whole-branch review
under the chosen execution skill. Subagent-driven execution is also available
if the user prefers per-task implementation/review contexts. Review this plan
and select an execution method before starting implementation.
