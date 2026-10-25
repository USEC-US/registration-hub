# Multi-stage Competition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended here) or superpowers:subagent-driven-development, according to the user's execution choice, to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run an ordered chain of the three supported formats, with locked advancement counts, computed qualifiers, saved unrestricted random successor draws, and safe corrections after downstream play.

**Architecture:** Extend the existing Stage/StageDraw/StageEntry lifecycle and competition commands. Stage-owned group plans exist before fixtures; draw-owned snapshots and source links preserve provenance. Keep placement calculation in format code, use one draw-scoped qualification/tie workflow, and integrate handoffs into the existing atomic publication/correction boundary.

**Tech Stack:** Python 3.12+, Django 6, PostgreSQL, Django Unfold, Svelte 5/SvelteKit, existing shadcn-svelte components, Paraglide EN/VI, Django tests, Vitest, and Playwright. No new dependency.

**Spec:** [Approved multi-stage design](../specs/2026-10-09-multi-stage-competition-design.md). Read it together with this plan; the older core design supplies unchanged match/history/privacy contracts.

## Global Constraints

- Any ordered combination of Round Robin, single elimination, and double elimination, including repeated formats; no branches, merges, Swiss, or cross-division entrants.
- Stage order, formats, group sizes, every advancement count, and qualification criteria lock at first-stage publication. Preserve allowed before-play scheduling and round/match series overrides.
- Retain the current supported bounds: 2–256 real entrants per draw, at most 16,384 ordinary generated matches per draw, and the existing extra-match budget. Series lengths remain integer 1–32767, odd for best-of.
- Every Round Robin group has at least two entrants, and `1 <= qualifying_places <= size`; sizes sum to the incoming field. Unequal sizes and unequal quotas are valid.
- All required ordinary matches and cutoff resolutions finish before a successor draw, including groups where everyone advances. Not-required conditional finals are exempt.
- Later draws use exactly the immediately preceding stage's eligible qualifiers. No ranking/manual handoff seeding, same-group exclusion, quota trimming, substituted entrants, or fictitious byes/finishers.
- Randomize once per explicit generation, persist the order, preview, and publish separately. GET and refresh never mutate; stale/repeated revisions cannot create an additional draw.
- Preserve permission checks, CSRF, division/competition locks, registration revalidation, signed correction impact, explicit reset consent, and atomic history.
- Draw replacement retains published identities/results as history; previously published stage identities remain public awaiting replacement. Draft data, actors, private reasons, and fingerprints stay private.
- Keep existing first-stage command calls and draw choices compatible. Already published single-stage competitions remain locked single-stage plans; no retroactive attachment.
- New match codes are `{stage.name}-M{ordinal}`, e.g. `Groups1-M1` and `Playoffs-M1`. Number once across each draw's groups/rounds/sections, then append extra matches; replacement draws restart at 1. Codes are labels, while numeric IDs identify records. Preserve all legacy stored codes.
- Withdrawal/disqualification commands, exceptional chain-ending commands, realtime, provider integration, automated scheduling, and registration/payment changes are excluded.

## File Ownership and Dependency Order

| Task | Owned changes | Depends on |
| --- | --- | --- |
| 1 | Model fields, stage-owned group plans, populated migration | Existing 0003 |
| 2 | Stage-aware setup, whole-plan validation and publication lock | 1 |
| 3 | Pure elimination finishing bands and cutoff classification | Existing elimination algorithms |
| 4 | Draw-scoped qualification/ties and correct stage completion | 1, 3 |
| 5 | Qualified successor draw generation and publication | 2, 4 |
| 6 | Cross-stage correction/revalidation and current-match guards | 4, 5 |
| 7 | Organizer stage setup, selection, ties, handoff and impact views | 2, 4–6 |
| 8 | Allowlisted multi-stage reads and historical match visibility | 4–6 |
| 9 | Public stage navigation, qualification and replacement states | 8 |
| 10 | Synthetic seeds, race/browser proof, operating notes and tracking | 7–9 |

`stage_commands.py` owns stage-plan edits/validation, `qualification.py` owns the shared draw-scoped qualification and tie workflow, and `handoff_commands.py` owns successor draw generation and source validity. These are concrete modules with the responsibilities above, not abstract services or a plugin system. Existing format command modules continue owning their generators. Existing `commands.py` integrates publication/results/corrections with these helpers.

Command tests reuse the existing `CompetitionCommandTests.setUp` and `_registration` pattern used by `RoundRobinCommandTests`; arrange each task's described stage/draw fixtures through real commands. The code snippets below pin assertions after those arrangements rather than introducing an additional fixture API.

## Review Focus

1. A future stage being valid in isolation but incompatible with its predecessor's quota: reject the whole chain before stage 1 publication (Task 2).
2. A score correction leaving qualifiers unchanged but reopening required source play or invalidating a tie: retire the suffix despite unchanged identities (Task 6).
3. A retired published match reached by direct URL: readable as history, every mutation rejected; a superseded private draft remains undiscoverable (Tasks 6 and 8).
4. A two-team group advancing both while its match is pending: qualification membership alone must not enable generation (Tasks 4 and 5).
5. Stage switching leaving an old group/round selected, or a direct action supplying another competition's stage: reset dependent filters and reject forged scope (Tasks 2, 7, and 9).

---

## Task 1: Persist plans and advancement provenance without replacing data

**Files:** Modify `server/competitions/models.py`, `server/competitions/tests/test_models.py`, and `server/competitions/tests/test_migrations.py`. Create `server/competitions/migrations/0004_multi_stage.py` from Django's generated migration and its reviewed data backfill.

**Interfaces produced:**

- `Stage.advancement_count: int | None`; nonfinal elimination quota, positive when present and permitted only for elimination formats.
- `StageGroupPlan(stage, number, name, size, qualifying_places)` with `Stage.group_plans`; unique stage/number and stage/name, positive number, size >= 2, and `1 <= qualifying_places <= size`.
- `StageDraw.source_draw: StageDraw | None` with protected `destination_draws`, and `source_fingerprint: str` (64-character digest or empty for no source). Source presence and fingerprint presence agree; forbid self-reference.
- `TieResolution.draw: StageDraw` with `StageDraw.tie_resolutions`; existing `group` becomes nullable. Commands later enforce group/draw/contender/parent consistency.
- `Match.code` becomes `CharField(max_length=128)` without global uniqueness. This holds the existing 100-character stage name and bounded suffix. Keep `unique_round_match` and all ID/FK constraints; do not add a redundant draw identifier or ordinal field to Match.

- [ ] **Write `MultiStageMigrationTests.test_populated_0003_upgrade_preserves_draws_and_backfills_rules`.** Seed a current published grouped draw, a superseded draft with different groups, confirmed/nested ties, and completed elimination matches using historical models. Assert group plans copy only the current draw's names, actual member counts and quotas; every old tie gets its owning draw; all old IDs, codes, scores, draw states, histories and publication timestamps survive. Add model constraint tests for invalid sizes/quotas and missing source/fingerprint pairs, plus duplicate display codes on distinct matches and a full-length Unicode stage prefix.

```python
# test_group_plan_rejects_quota_above_size: stage is an arranged draft RR stage.
with self.assertRaises(IntegrityError), transaction.atomic():
    StageGroupPlan.objects.create(
        stage=stage, number=1, name="A", size=2, qualifying_places=3
    )
```

- [ ] **Run the new model/migration tests before implementation.** From `server/`: `uv run python manage.py test competitions.tests.test_models competitions.tests.test_migrations --noinput`. Expect failures for missing fields/migration; keep tests restoring the latest migration graph in cleanup, as current migration tests do.
- [ ] **Add fields/constraints and the migration.** Backfill draw ownership while the new FK is nullable, then make it required. Copy plans from each stage's current draw without linking historical group snapshots to mutable plans. Alter only the code field's schema, leaving its stored strings untouched. Leave legacy outgoing elimination quotas/source links null; never generate fixtures or infer an unrecorded handoff during migration.
- [ ] **Run the same tests, then `uv run python manage.py makemigrations --check --dry-run`.** Expect passing preservation/constraint tests and no migration drift. Review reverse operations: new multi-stage data would be lost, and repeated/long display codes cannot satisfy the old schema; operating notes must require matching backup/code restore rather than a live downgrade.
- [ ] **Commit only these model/migration/test files:** `feat(competitions): persist stage plans and draw provenance`.

## Task 2: Make setup stage-aware and freeze a valid whole chain

**Files:** Create `server/competitions/stage_commands.py` and `server/competitions/tests/test_stage_plan.py`. Modify `server/competitions/command_support.py`, `server/competitions/commands.py`, `server/competitions/round_robin_commands.py`, and affected setup/draw regressions in `test_commands.py` and `test_round_robin_commands.py`. Update the generated-code assertion in `test_api.py` in this task.

**Interfaces:**

- Add `_stage_for_command(competition: Competition, stage_id: int | None = None) -> Stage` in `command_support.py`: omitted identity means stage 1; supplied identity must belong to the locked competition.
- Extend `configure_elimination` and `configure_round_robin` with keyword `stage_sequence: int = 1`. Configure/create that sequence using current format validation; never create a hole after publication. Existing callers remain valid.
- In `stage_commands.py`, implement `set_stage_advancement(*, actor, stage_id: int, expected_revision: int, advancement_count: int | None) -> Stage`, `set_stage_groups(*, actor, stage_id: int, expected_revision: int, group_specs: Sequence[tuple[str, int, int]]) -> list[StageGroupPlan]` (name, size, quota), `reorder_stages(*, actor, competition_id: int, expected_revision: int, stage_ids: Sequence[int]) -> list[Stage]`, and `remove_stage(*, actor, stage_id: int, expected_revision: int) -> None`.
- `validate_stage_plan(competition: Competition) -> list[dict]` returns sequence-ordered `stage_id`, `incoming_count`, `outgoing_count` and `ordinary_match_count`; raises `ValidationError` on the first incompatible rule. Final `outgoing_count` is null.
- Extend `save_elimination_draw`, `save_round_robin_draw`, and `publish_draw` with `stage_id: int | None = None`; later-stage direct draw writes are rejected until Task 5 provides the guarded handoff path.
- Existing format builders write `{stage.name}-M{ordinal}` in their saved creation order. Elimination counts all sections continuously; Round Robin continues across groups. Under the existing competition lock, a fixture batch begins after the count of every retained match in its draw and increments per created match; no code parsing or new counter record is needed. Keep round-local `Match.number` and source-slot addressing unchanged. Names remain subject to current validation and need no new uniqueness rule or prefix control.

- [ ] **Write failing plan tests.** `test_whole_plan_rejects_incompatible_future_groups_without_publication` uses eight initial entrants, a six-qualifier source, and a destination planned as 3/3/2: assert publication fails, timestamps remain null, revision/history unchanged. `test_arbitrary_partitions_and_unequal_quotas` exercises 3/3/2 with 2/2/2, 3/2/2 with 2/2/2, and 2/5/3 with 1/4/2; assert incoming/outgoing counts 8→6, 7→6, and 10→7. Enumerate ordered small partitions with every size >= 2 and valid quotas, checking the same equations. Test booleans/nonintegers, zero/oversized quotas, one-qualifier successors, unsupported formats, budget limits, and another competition's stage ID.
- [ ] **Write `test_match_labels_number_once_per_draw` for grouped and single/double-elimination fixtures.** Assert exact contiguous labels in saved match creation order, including byes/conditional finals, and reset to M1 on draft replacement with distinct IDs. Change the existing API expectation for its newly generated fixture to `Final bracket-M1`; legacy migration fixtures keep their old codes.

```python
# A configured eight-entry 3/3/2 source with quota two, then final elimination.
rows = validate_stage_plan(competition)
self.assertEqual([row["incoming_count"] for row in rows], [8, 6])
self.assertEqual([row["outgoing_count"] for row in rows], [6, None])
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_stage_plan --noinput`.** Expect missing-interface or validation assertion failures.
- [ ] **Implement locked plan commands and stage-aware callers.** Use existing permissions, division/competition lock, revision and `_record_change`; configuration may create only the next contiguous sequence, and reordering uses collision-safe updates under one transaction requiring every stage exactly once. Removal is prepublication only and rejects a stage with retained draws; delete its mutable group plans, retain an audit snapshot, and renumber the remaining plan. Future stages have no draws yet. Changing unlocked setup invalidates affected drafts. First publication validates all expected fields and locks structural/qualification edits through the immutable stage-1 timestamp. Source-independent format options retain current validation. Legacy first-stage grouped draw calls may derive group plans from the actual saved allocation before the lock; explicit plans must match saved membership sizes. A final elimination quota is null; a nonfinal one is required.
- [ ] **Run plan and existing setup tests:** `uv run python manage.py test competitions.tests.test_stage_plan competitions.tests.test_commands competitions.tests.test_round_robin_commands competitions.tests.test_double_elimination_commands competitions.tests.test_api --noinput`. Assert no future fixtures are generated by configuration/first publication and existing first-stage caller defaults still work.
- [ ] **Commit:** `feat(competitions): validate and lock ordered stage plans`.

## Task 3: Calculate elimination finishing bands from real results

**Files:** Modify `server/competitions/elimination.py`. Create `server/competitions/tests/test_placements.py`.

**Interfaces produced in `elimination.py`:**

- Frozen `EliminationResult(round_number: int, section: str, status: str, outcome: str, side_one_id: int | None, side_two_id: int | None, winner_id: int | None)`.
- Frozen `PlacementBands(bands: tuple[tuple[int, ...], ...], unranked_entry_ids: tuple[int, ...])`. Bands run best to worst; an unresolved band carries equal finishing placement. IDs are source StageEntry IDs.
- `finishing_bands(entry_ids: Sequence[int], results: Sequence[EliminationResult], *, format: str) -> PlacementBands`; pure calculation, no database writes. Inputs include ordinary matches only; incomplete required play is handled by Task 4 before calling it.

- [ ] **Write table-driven failing placement tests.** An eight-entry ordinary single bracket must yield band sizes `(1, 1, 2, 4)`; Top-3 therefore needs one of the two IDs in band 3, while Top-4 includes both. Double brackets must rank the actual final loser second and later terminal lower losses above earlier losses under both final policies. Include 2, 3, 5 and 6 entrants, structural byes, real single forfeits, lower-round double forfeits, and a deciding grand-final double forfeit with no invented champion. Exclude tiebreak/structural empty entrants from ordinary placements.

```python
def test_two_entry_single_finishing_bands(self):
    table = finishing_bands(
        [11, 12], [EliminationResult(1, "NORMAL", "FINAL", "PLAYED", 11, 12, 11)],
        format="SINGLE_ELIMINATION",
    )
    self.assertEqual(table.bands, ((11,), (12,)))
    self.assertEqual(table.unranked_entry_ids, ())
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_placements --noinput`.** Expect missing calculation failures.
- [ ] **Implement finishing bands alongside the generators.** For single elimination use terminal ordinary-round exit depth. For double elimination use the actually required deciding final, then terminal lower-round exits. When an upper double forfeit makes lower placement undefined, return only provably leading bands and put remaining uncertain real entries in `unranked_entry_ids`; do not guess where that exit belongs. Every input entry must occur exactly once across bands/unranked entries. Ordering inside a tied band is stable for display and has no competitive meaning.
- [ ] **Run placement and existing generator tests:** `uv run python manage.py test competitions.tests.test_placements competitions.tests.test_elimination --noinput`. Assert a reset marked NOT_REQUIRED never decides placement and an activated final does.
- [ ] **Commit:** `feat(competitions): calculate elimination placement bands`.

## Task 4: Unify draw-scoped qualification and cutoff tie resolution

**Files:** Create `server/competitions/qualification.py` and `server/competitions/tests/test_qualification.py`. Modify `server/competitions/round_robin_commands.py`, `server/competitions/commands.py`, `test_round_robin_ties.py`, and `test_round_robin_commands.py`.

**Interfaces:**

- Consume `finishing_bands` from Task 3 and current `group_standings`/ranking calculations.
- `stage_qualification(draw: StageDraw, *, projected_matches: Mapping[int, dict] | None = None) -> dict` returns `qualification_state` (PROVISIONAL/AWAITING_RESOLUTION/RESOLVED/BLOCKED), `qualifier_entry_ids: list[int]`, `fingerprint: str`, `block_reason: str | None`, `bands: list[list[int]]`, and `cutoffs: list[dict]`. Each cutoff has `group_id: int | None`, `entry_ids: list[int]`, `places: int`, `parent_resolution_id: int | None`, `resolution_id: int | None`, and `source_fingerprint: str`. `projected_matches` maps match IDs to projected status, outcome, scores and winner entry ID, including every dependent reset; it never writes. Adapt the existing group result-projection path without breaking its current callers.
- `preview_qualification_tie(*, actor, draw_id: int, expected_revision: int, tied_entry_ids: Sequence[int], method: str, group_id: int | None = None, ordered_entry_ids: Sequence[int] = (), series_length: int = 1, parent_resolution_id: int | None = None) -> dict` returns the current signed preview/fixture shape.
- `confirm_qualification_tie(*, actor, token: str, internal_reason: str = "") -> TieResolution`; return current recorded resolution, no automatic nested contest generation.
- Preserve `preview_group_tie` and `confirm_group_tie` as compatibility entry points to this shared behavior. Move the existing tie implementation to its owning module rather than copying it. Keep the existing group ranking/fingerprint code where it belongs, with one cutoff-selection implementation used by group and elimination scopes.

- [ ] **Write failing qualification tests.** `test_all_qualifying_group_still_waits_for_required_play` uses a two-entry group with quota two and one pending match: assert PROVISIONAL, then RESOLVED after final play with both qualifiers and no ordering tie. `test_elimination_top_three_requires_cutoff_choice` asserts the two semifinal losers and one available place, resolves both manual and extra-contest paths, and excludes untied contenders. Assert quota-all can qualify all eligible real entries without ordering an uncertain band, but a cutoff requiring undefined upper-double-forfeit placement yields BLOCKED with a reason. Add recursive extra ties, forged parent/group/draw, stale confirmations, manual reason, and extra-match budget checks.
- [ ] **Add extra-match label regressions.** Tie fixtures continue the draw-wide ordinal after all saved fixtures, even when an earlier resolution was superseded; assert no within-draw label reuse or renumbering of ordinary/historical fixtures for both group and elimination cutoffs.

```python
# A published two-entry group, quota two, ordinary match not yet final.
snapshot = stage_qualification(source_draw)
self.assertEqual(snapshot["qualification_state"], "PROVISIONAL")
self.assertEqual(snapshot["cutoffs"], [])
```

- [ ] **Run new and existing tie tests:** `uv run python manage.py test competitions.tests.test_qualification competitions.tests.test_round_robin_ties --noinput`. Expect failures for missing generalized interfaces before the refactor.
- [ ] **Implement the shared qualification/tie path.** Reuse saved contenders, source fingerprints, signed previews, nested decisions and the current decisive mini-table. All required ordinary fixtures must be final or explicitly not required; source membership known early is insufficient. Only cutoff bands require resolution. Extra matches append Task 2's labels under the same lock, without ordinary winner/loser routes, and cannot become the apparent main final in `_update_stage_completion`. A final elimination stage without outgoing quota retains normal champion/no-champion completion; final Round Robin retains its existing group qualification semantics. Refresh does not mutate resolutions.
- [ ] **Run qualification, result and tie regressions:** `uv run python manage.py test competitions.tests.test_qualification competitions.tests.test_round_robin_ties competitions.tests.test_round_robin_commands competitions.tests.test_commands competitions.tests.test_double_elimination_commands --noinput`. Verify completion/fingerprint equivalence for unchanged ranking inputs and invalidation for changed relevant inputs.
- [ ] **Commit:** `feat(competitions): resolve qualification cutoffs across formats`.

## Task 5: Generate and publish successor draws from exact qualifiers

**Files:** Create `server/competitions/handoff_commands.py` and `server/competitions/tests/test_handoffs.py`. Modify shared/format commands in `commands.py`, `round_robin_commands.py`, and `command_support.py` only where they own stage/draw validation and fixture persistence.

**Interfaces:**

- `generate_next_stage_draw(*, actor, stage_id: int, expected_revision: int, regenerate: bool = False) -> StageDraw` in `handoff_commands.py`.
- `validate_draw_source(draw: StageDraw) -> dict` returns Task 4's current source snapshot or raises `ValidationError` for wrong predecessor, stale source, unfinished qualification, ineligibility, or mismatched membership.
- The two existing saved-draw builders use a shared stage-local persistence seam accepting a locked stage and exact source entrants; this internal seam is not a second externally callable bypass. First-stage public commands keep their legacy shapes.
- Successor fixture generation reuses Task 2's labels. Repeated format/name stages and replacement draws may reuse display labels while retaining different match IDs; stage/draw version and historical context identify the correct record.
- `publish_draw(..., stage_id=None)` now permits valid replacement publication when the stage was previously public and has no current published draw; it keeps `Stage.published_at` unchanged.

- [ ] **Write failing handoff tests for all nine source/destination combinations.** Pin one system shuffle to a known permutation and assert source-entry identity, saved positions, exact set membership, no rank-driven order, one source link/fingerprint and one current draw. For 3/3/2 and 3/2/2 quota-two sources, assert six entries and two byes in the next single bracket; for a six-entry destination Round Robin with sizes 2/4, assert those exact group sizes. Test all-qualified pending play, unresolved ties, missing quota, wrong predecessor, inactive/rejected registration, duplicate/cross-division entries, direct later-stage save bypass, repeated revision, and publication after source data changed.

```python
# Completed quota-two groups and a configured, undrawn single-elimination successor.
draw = generate_next_stage_draw(
    actor=self.actor, stage_id=destination.pk, expected_revision=competition.revision
)
self.assertEqual(draw.entries.count(), 6)
self.assertEqual(Match.objects.filter(round__draw=draw, outcome="BYE").count(), 2)
self.assertEqual(draw.source_draw_id, source_draw.pk)
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_handoffs --noinput`.** Expect missing-command/guard failures.
- [ ] **Implement under division/competition locks and `transaction.atomic`.** Resolve actual eligible qualifiers, shuffle through `secrets.SystemRandom`, persist each `source_entry`, partition later Round Robin by locked sizes, and invoke existing fixture generators. An existing draft returns unchanged with no new audit revision; explicit `regenerate=True` supersedes it and creates a recorded version. Never regenerate a published current draw. Stage 1 publication still checks the selected registration pool; later publication checks that draw's exact qualified entrants rather than the full first-stage selection. Publication and generation independently revalidate approved registrations under their shared lock.
- [ ] **Run handoff and command regressions:** `uv run python manage.py test competitions.tests.test_handoffs competitions.tests.test_commands competitions.tests.test_round_robin_commands competitions.tests.test_double_elimination_commands --noinput`. Add one three-stage chain and repeated stage names; assert each draw starts at M1 with distinct match IDs, no successor fixture exists before the allowed POST, and reading previews never changes order/revision.
- [ ] **Commit:** `feat(competitions): generate saved random stage handoffs`.

## Task 6: Extend signed correction impact through the dependent suffix

**Files:** Modify `server/competitions/commands.py`, `round_robin_commands.py`, and `handoff_commands.py`. Create `server/competitions/tests/test_stage_corrections.py`; extend `test_concurrency.py` for correction/advancement contention.

**Interfaces:**

- `project_handoff_corrections(source_draw: StageDraw, *, projected_qualification: dict, source_needs_replay: bool) -> dict` in `handoff_commands.py`; read-only result contains `retained_draw_ids`, `superseded_draw_ids`, `reset_matches` (full existing snapshots), and new source fingerprints for retained draws.
- Existing `_correction_payload`, `_correction_preview_response`, `review_correction_preview`, and `apply_correction` carry this canonical `handoff_impact` in the signed token and recompute it under locks. Existing public signatures remain valid.
- `_lock_match`/current-match validation rejects a superseded draw in every schedule, series, start, progress, finalization, and correction mutation; historical reads use a separate visibility boundary in Task 8.

- [ ] **Write failing correction tests.** `test_unchanged_valid_qualifiers_preserve_played_successor` asserts identical destination IDs/order/groups/scores plus updated fingerprint and recorded revalidation. `test_unchanged_set_but_reopened_source_retires_suffix` and `test_invalidated_tie_retires_suffix` pin Review Focus 2. `test_changed_qualifiers_retire_two_played_successors_atomically` checks exact signed impact, preserved historical scores/applied lengths, awaiting stage states, unchanged first-publication timestamps, and replacement draws only after replay/resolution. Inject a write failure and assert complete rollback. Exercise elimination, group, and extra-match source corrections.

```python
# After confirming a qualifier-changing correction of a source feeding two played stages.
destination_draw.refresh_from_db()
third_draw.refresh_from_db()
played_match.refresh_from_db()
self.assertEqual(destination_draw.state, "SUPERSEDED")
self.assertEqual(third_draw.state, "SUPERSEDED")
self.assertEqual((played_match.side_one_score, played_match.side_two_score), (2, 0))
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_stage_corrections --noinput`.** Expect missing suffix impact/current-match guard failures.
- [ ] **Implement the suffix projection and atomic application.** Pass all projected upstream resets from `_project_correction` through `stage_qualification(..., projected_matches=...)`, not only its corrected result; a source needing replay cannot keep a handoff. Preserve later draws only with valid complete source and unchanged eligible sets. Otherwise supersede the whole dependent suffix, retaining results in old rows/history rather than clearing historical rows. Extend explicit consent checks to live/final results in retired draws. Recompute canonical impact and reject mismatches. Emit safe public reset summaries only for formerly public draws; draft provenance remains private.
- [ ] **Run correction and concurrency tests:** `uv run python manage.py test competitions.tests.test_stage_corrections competitions.tests.test_concurrency competitions.tests.test_round_robin_ties competitions.tests.test_commands competitions.tests.test_double_elimination_commands --noinput`. Assert direct mutation of every retired match action fails and one winning transaction determines advancement/correction races.
- [ ] **Commit:** `feat(competitions): preserve and invalidate handoffs during corrections`.

## Task 7: Operate complete stage plans in the existing organizer workspace

**Files:** Modify `server/competitions/admin.py`, `admin_workspace.py`, `forms.py`, existing templates under `server/competitions/templates/admin/competitions/`, `static/competitions/forms.js`, and `static/competitions/workspace.css`. Extend `test_workspace.py` and `test_admin.py`; use a focused new template only if the existing action/confirmation templates cannot express the plan form.

**Interfaces:**

- Extend `workspace_url(competition_id, tab=None, *, stage_id=None)` with encoded `tab` then `stage` parameters and preserve selected stage in all tab/action/return links.
- Add `StageGroupPlanForm` (name, size, quota), `StageAdvancementForm` (nullable only for a final elimination stage), `StageOrderForm` (all stage IDs exactly once), and draw-scoped `QualificationTieForm`; reuse RevisionForm and existing confirmation/reason controls.
- CompetitionAdmin provides guarded actions for configuring a sequence, setting group plans/quotas, reordering/removing unused prepublication stages, generating/regenerating the selected next draw, previewing/publishing, and draw-scoped tie preview/confirmation. Old group tie URLs still delegate correctly.

- [ ] **Write failing organizer tests.** `test_stage_context_survives_forms_and_return_links` checks exact hrefs, stage/group/round reset on selection change, and cross-competition stage rejection. `test_plan_publication_preview_explains_whole_lock` checks displayed incoming/outgoing counts and locked setup actions after publication. `test_generate_successor_requires_complete_source` covers disabled controls plus forged POST rejection. Add extra/manual elimination cutoff actions, replacement preview and downstream reset lists, permission combinations, CSRF and mutation-free GET.

```python
expected = reverse("admin:competitions_competition_change", args=[competition.pk])
self.assertEqual(
    workspace_url(competition.pk, "standings", stage_id=stage.pk),
    f"{expected}?tab=standings&stage={stage.pk}",
)
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_workspace competitions.tests.test_admin --noinput`.** Expect absent plan/handoff controls and wrong stage context.
- [ ] **Implement by composing existing workspace/action templates.** Keep first-stage entrant selection separate from later read-only qualifier lists. Move group definitions into stage setup; first-stage GroupDrawForm consumes the configured groups for its existing membership choices, later groups use random assignments. Names such as Generate next stage draw and Draw position replace handoff seeding language. Display waiting, blocked, tie, private preview and awaiting-replacement states with specific next actions. Preserve no-JavaScript form submissions and `.cw-bracket-scroll` containment.
- [ ] **Run organizer tests and relevant command tests.** Verify a view-only organizer can inspect permitted stages but cannot create/confirm/retire, and resetting played downstream matches requires both existing correction permissions. Verify root page width remains contained in the later browser proof.
- [ ] **Commit:** `feat(admin): operate ordered competition stages`.

## Task 8: Publish safe qualification and historical stage reads

**Files:** Modify `server/competitions/serializers.py` and `views.py`; extend `server/competitions/tests/test_api.py` and relevant concurrent snapshot tests.

**Interfaces:**

- Add `PublicStageSerializer.qualification`: null for a final elimination stage; otherwise an allowlisted object with `state`, `advance_count` (null for per-group rules), `qualifiers: PublicCompetitionEntry[]`, `placement_bands: PublicCompetitionEntry[][]`, and draw-level `cutoff_ties` (public contender/decision/extra-round data only). Round Robin retains its existing per-group quotas/standings/tie payloads.
- Add `PublicStageSerializer.draw_state`: `PUBLISHED` or `AWAITING_REPLACEMENT`, derived from the current draw rather than exposing private draft states. Keep existing status/champion/seed/API fields.
- Extend existing `draw_published` with safe source-stage context and existing `result_corrected` with an allowlisted `handoff_impact` containing retired stage/draw identifiers and preserved public result snapshots. Use `qualification_tie_confirmed` for elimination cutoffs and preserve existing `group_tie_confirmed` for compatibility. Handoff generation/revalidation remains private; publication reveals only published entrant/source-stage labels.
- `PublicMatchView` may return a superseded match only when its draw has a nonnull prior `published_at`, its stage was published, and its parent tournament is public. Current round endpoints still exclude retired rounds. Unpublished IDs and history filters return 404.

- [ ] **Write failing API tests.** Retired public stages remain listed with no active entries/fixtures and an awaiting-replacement state; retired published match detail is historical with preserved scores; superseded private draft matches remain 404 even for logged-in organizers. Check source draw IDs/fingerprints, actor IDs, reasons, private registration/payment fields and future group plans are absent. Test public quota/tie payloads, stage-filtered Changes, mixed-revision reads, and a later draw in private replacement preview. New and legacy code strings pass through unchanged; repeated labels resolve to the correct numeric match IDs and retain their history context.

```python
# A published destination draw was superseded, and a private replacement is saved.
response = self.client.get(f"/api/competition-stages/{destination.pk}/")
self.assertEqual(response.status_code, 200)
self.assertEqual(response.data["draw_state"], "AWAITING_REPLACEMENT")
self.assertEqual(response.data["entries"], [])
self.assertEqual(response.data["rounds"], [])
```

- [ ] **Run `uv run python manage.py test competitions.tests.test_api --noinput`.** Expect missing fields or historical visibility failures.
- [ ] **Implement explicit serializers and bounded prefetches.** Reuse `consistent_public_read` and published-stage identity filtering. Compute qualification from prefetched current data, not per-fixture extra queries. For waiting replacement return empty active arrays and safe state; do not reveal a private replacement draw. Reuse the existing `historical: bool` serializer/type and extend its visibility path to formerly published retired draws; do not add a second flag or change ordinary match cards.
- [ ] **Run API and coherent-read tests:** `uv run python manage.py test competitions.tests.test_api competitions.tests.test_concurrency --noinput`. Assert a concurrent atomic correction cannot expose new source qualification with old current destination fixtures.
- [ ] **Commit:** `feat(api): expose safe multi-stage qualification and history`.

## Task 9: Select and explain public stages without mixing their context

**Files:** Modify `web/src/lib/api/types.ts`, `web/src/lib/api/competitions.ts` only if needed for the existing contract, `web/src/routes/tournaments/[slug]/games/[gameId]/bracket/+page.ts` and `+page.svelte`, `web/messages/en.json`, and `web/messages/vi.json`. Extend `web/src/routes/bracket-page.test.ts`, `bracket-page.svelte.spec.ts`, and `web/src/lib/api/competitions.test.ts` where new API fields are asserted.

**Interfaces:** Type the Task 8 qualification/draw-state payloads and retain the existing historical match type. The bracket page uses a published stage ID selection, never an array-position assumption. Initial selection is the requested valid `?stage=<id>` or the highest-sequence published stage with a current published draw; if all await replacement, use the highest-sequence published stage. Reset group/round selection whenever the selected stage changes; reject an invalid requested stage with the existing unavailable navigation state.

- [ ] **Write failing loader/component tests.** Select two published stages with overlapping round numbers/group names and distinct IDs; assert labels, matches, qualification, group/round controls and current-stage context always use the selected stage. Switch a grouped stage to elimination and assert no stale group remains. Cover invalid stage query, early hydration controls, awaiting replacement with empty arrays, cutoff ties, EN/VI text, preserved revision retry, historical match labels, and stage-specific Changes references. Use the existing browser component setup/components rather than introducing a UI framework.

```typescript
// After rendering two published stages and choosing Playoffs in the existing browser harness.
await page.getByLabel('Stage').selectOptions(String(playoffs.id));
await expect.element(page.getByRole('heading', { name: 'Playoffs', exact: true })).toBeVisible();
await expect.element(page.getByLabel('Group')).not.toBeInTheDocument();
```

- [ ] **Run from `web/`: `pnpm exec vitest run src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts src/lib/api/competitions.test.ts`.** Expect missing stage controls/fields or stale-context assertions.
- [ ] **Implement selection and copy with existing Select/Field/Alert/table patterns.** Respect the loader's consistent snapshot. Build match labels across all published stages keyed by numeric match IDs so repeated labels and historical Changes identify the correct record; render fixtures/standings only for the selected stage and existing bounded selected round. Display stored codes directly, including stage-prefixed and legacy labels, with historical context for retired matches. Qualifying ties are distinct from harmless tied ordering; random draw positions are not ranked seeds. Publish no draft placeholder stages or hidden draft fixtures. Update relevant existing synthetic API fixtures with additive fields.
- [ ] **Run the focused Vitest command, `pnpm check`, changed-file Prettier/ESLint, and `pnpm build` with the established environment.** Expect passing assertions and no new type/i18n errors. Use existing accessible components, hydration protection, full-image behavior if affected, and contained bracket scrolling; no unrelated UI rewrite.
- [ ] **Commit:** `feat(web): navigate published competition stages`.

## Task 10: Prove generalized rules, races and complete organizer/public journeys

**Files:** Modify `server/registrations/dev_seed.py`, `server/registrations/tests/test_seed_dev_data_command.py`, `server/e2e/serve.py`, `server/competitions/tests/test_concurrency.py`, `web/e2e/django/admin-bracket.spec.ts`, and `web/e2e/django/bracket.spec.ts`. Reuse the existing private fixture writer in `server/e2e/fixtures.py` unchanged. Create `docs/testing/competition-multi-stage.md`. Update scope/status notes in `docs/BRACKET-TODO.md` and `docs/testing/competition-round-robin.md` only after actual proof.

**Interfaces:** Add command-owned `dev-usec-multi-stage` synthetic fixtures and browser fixture identifiers to the existing harness. No personal/workbook data, hardcoded database IDs, real payment destination, production reset, or new test runner. Use actual guarded commands to configure, lock, score, resolve and generate the chain.

- [ ] **Write failing integration tests.** A synthetic 3/3/2→six-team playoffs journey configures the plan, publishes, blocks early advancement, finishes all groups, resolves a cutoff, generates/previews/publishes a saved random draw, and scores a playoff. A correction changes a source qualifier and retires the played suffix; spectators retain old results in Changes/historical match detail and see awaiting replacement. Add 3/2/2 and 2/5/3 unequal-quota command examples, a Top-3 elimination tie feeding Round Robin, and a three-stage chain. Seed reruns must preserve published IDs/results and unrelated fixtures.

```typescript
// In the multi-stage Playwright journey, after a source correction retires the playoffs.
await page.getByLabel('Stage').selectOption(String(fixture.playoffsStageId));
await expect(page.getByText('Awaiting replacement draw', { exact: true })).toBeVisible();
await expect(page.getByText(fixture.preservedResultSummary, { exact: true })).toBeVisible();
expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
```

- [ ] **Run the new focused seed/race tests and selected Django-backed browser journeys to observe failures before adding fixtures/actions.** Browser command from `web/`: `pnpm exec playwright test --config=playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts --grep 'multi-stage'`. This harness creates disposable PostgreSQL/media; do not point it at production.
- [ ] **Implement the synthetic fixtures and remaining integration/race assertions.** Use the existing PostgreSQL thread/barrier harness for generate/generate, publish/source-correction, manual-tie/correction and eligibility-change/generate races; assert a single valid outcome and no partial history. Browser assertions cover 390px width, keyboard stage/group controls, EN/VI, no-JavaScript organizer posts where applicable, exact stage return URLs, no draft leakage, and history after a played-suffix reset.
- [ ] **Run the assembled focused proof.** From `server/`: `uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command --noinput`; `uv run python manage.py check`; `uv run python manage.py makemigrations --check --dry-run`; `uv run ruff check competitions e2e registrations/dev_seed.py registrations/tests/test_seed_dev_data_command.py`. From `web/`: the Task 9 Vitest command, `pnpm check`, `pnpm build`, and the targeted Playwright command above plus existing elimination/registration journeys if shared harness behavior changed. Reuse a test-only Turnstile key and static collection when required by current settings. PostgreSQL/concurrency proof cannot be replaced by SQLite; report environment blockers separately. Stop expanding checks once these pass unless a failure/change justifies another run.
- [ ] **Record actual evidence and commit:** `test(competitions): verify generalized multi-stage workflows`. Operating notes explain plan locking, all-required-play, random bye allocation, explicit tie methods, undefined upper-double-forfeit placement blocking, atomic suffix retirement, draw-scoped display labels, migration backup/forward-fix policy, and published single-stage compatibility. Mark H1 and only delivered UI/read items complete; do not mark Swiss/withdrawal/chain-end work complete.

## Plan Self-review and Execution Handoff

Coverage: spec sections 1–2 → Tasks 1, 2, 5; section 3 → Tasks 3–4; section 4 → Task 5; section 5 → Tasks 1–6; section 6 → Task 6; section 7 → Tasks 7–9; section 8 → Tasks 1, 2, 10; section 9 → each owning task plus Task 10. Each Review Focus item has a named regression in its owning task. No implementation is represented by this document's checkboxes yet.

Runtime work starts after the user reviews this plan and selects execution. Recommend **Native** execution: the format commands, publication, qualification, and correction seams change sequentially across shared files, so one implementer can keep those interfaces consistent; one fresh reviewer checks the complete branch afterward. Subagent-driven task-by-task implementation/review is also available if the user chooses it. Determine checkout isolation at execution time through the using-git-worktrees environment checks and preserve unrelated edits.
