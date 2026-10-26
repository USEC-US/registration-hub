# Competition Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use Markdown checkboxes for tracking.

**Goal:** Deliver auditable withdrawal/disqualification, restoration, exceptional competition endings and reopening across every supported format, with organizer/public workflows and fresh release evidence.

**Architecture:** Extend the existing command, revision, signed-preview and projection patterns. Retain ChangeSet history, add minimal operational provenance for reversals, and distinguish a frozen Swiss round's eligibility inputs from today's eligible field. Use the current Unfold workspace and public SvelteKit bracket.

**Tech Stack:** Django 6, PostgreSQL, Python >=3.12 excluding 3.14.1, pinned NetworkX 3.7, Svelte 5/SvelteKit, Vitest and Playwright; no new dependencies.

**Spec:** [Approved competition lifecycle design](../specs/2026-10-26-competition-lifecycle-design.md).

**Status:** Implemented and independently reviewed on 2026-10-26 using the user-approved subagent workflow and task-scoped commits. Tasks 1–9 and bracket-core V1–V5 are complete. Release evidence and remaining limits are recorded below and in the [operating guide](../../testing/competition-lifecycle.md).

## Global Constraints

- Preserve results preceding removal; any reset of later played results requires a signed impact preview and explicit confirmation.
- Restoring an entrant undoes still-authoritative removal-caused forfeits, including those generated later, while preserving independent organizer corrections.
- Reopening keeps retired fixtures historical; replacement draws need fresh previews and explicit publication.
- Never silently promote a lower finisher, change a quota, relax locked rules, or substitute another registration.
- Preserve frozen public identity and original stage seeds, rules and Swiss round limits.
- Use TournamentGame → Competition → affected-record locks; one command increments revision and appends history once.
- Keep actor identity, private reasons, draft IDs, provenance and registration/payment data out of public responses.
- Support all five stage formats, public English/Vietnamese and 390px containment; organizer controls remain English.
- Keep 2–256 entrants, at most 16,384 ordinary matches per draw and at most 64 Swiss rounds.
- No realtime, providers, TFT, registration/payment redesign, merge or production deployment.
- Follow repository CodeGraph-first navigation. Preserve unrelated changes and commit only the task's owned files.

## Review Focus

1. Withdrawal after a Swiss round was published must not make its historical eligibility fingerprint appear stale; Task 3 tests this before and after later result correction.
2. Two independent removals or a later manual correction must not let restoration overwrite somebody else's result decision; Task 4 tests both orders and snapshot ownership.
3. An inactive qualifier still inside an earned cutoff must block the handoff instead of silently promoting the next finisher; Tasks 3–4 test tied and untied cutoffs.
4. A direct command or stale form must not mutate an ended competition; Task 5 exercises every command family, and Task 9 races ending against scoring/publication.
5. Unpublished suffixes and private rounds must stay absent from public ending/restoration history, while previously public retired match links still work; Task 7 tests both endpoints and rendered history.

## File ownership and shared contracts

Use existing files except for the focused additions below:

| Owner | Files | Responsibility |
| --- | --- | --- |
| Persistence | `server/competitions/models.py`, `migrations/0006_competition_lifecycle.py` | Ending state, removal provenance references and Swiss availability snapshots |
| Result projection | new `server/competitions/result_projection.py`; existing `commands.py` | Shared elimination projection/application for result corrections and lifecycle actions |
| Lifecycle commands | new `server/competitions/lifecycle_commands.py`; existing `command_support.py` | Signed transition/end/reopen previews, atomic apply, provenance and mutation guard |
| Formats | existing `swiss.py`, `swiss_commands.py`, `swiss_corrections.py`, `qualification.py`, `round_robin_commands.py`, `handoff_commands.py` | Availability-aware progression, qualification and historic fingerprints |
| Organizer | existing `admin.py`, `admin_workspace.py`, `forms.py`, workspace/action templates | Existing workspace actions and impact confirmations |
| Public | existing serializers/views, API types, bracket page and locale messages | Allowlisted lifecycle state and Changes |
| Proof | focused new lifecycle test files, existing migrations/concurrency/browser/seed tests and operating docs | Behavior, upgrade, privacy, contention and full journeys |

Command interfaces live in `lifecycle_commands.py`; actor follows existing organizer APIs:

```python
def preview_entrant_transition(*, actor, entrant_id: int,
    expected_revision: int, status: str) -> dict: ...
def apply_entrant_transition(*, actor, token: str, internal_reason: str,
    confirm_live_forfeits: bool = False, confirm_resets: bool = False) -> CompetitionEntrant: ...
def preview_competition_end(*, actor, stage_id: int, expected_revision: int,
    award_sole_survivor: bool = False) -> dict: ...
def apply_competition_end(*, actor, token: str, internal_reason: str,
    confirm_resets: bool = False) -> Competition: ...
def preview_competition_reopen(*, actor, competition_id: int,
    expected_revision: int) -> dict: ...
def apply_competition_reopen(*, actor, token: str, internal_reason: str,
    confirm_resets: bool = False) -> Competition: ...
def review_lifecycle_preview(*, actor, token: str) -> dict: ...
```

Preview responses contain `token`, `kind`, `before`, `after`, `match_impacts`,
`live_forfeit_ids`, `reset_match_ids`, `retired_draws`, `retired_rounds`,
`blocked_handoffs`, and `preserved_corrections`. IDs are sorted, scoped and
computed on the server. A separate salt, `competitions.lifecycle`, binds the
operation, competition, revision, subject and canonical impact. Apply functions
reject malformed tokens, wrong operation, stale impact and missing strict-boolean
consent; the client never supplies the authoritative reset list.

### Verification environment

At execution, use an isolated checkout according to the worktree skill. Reuse
installed dependencies and a disposable PostgreSQL instance, never copied live
credentials. Create test-only `/tmp/hcmusec_lifecycle_settings.py` importing
`config.settings` and overriding the database to an explicitly disposable local
database, a test-only Turnstile key, and STATIC_ROOT under `/tmp`. Collect static
files before admin rendering. Use `UV_CACHE_DIR=/tmp/hcmusec-lifecycle-uv-cache`.

Commands below run in `server/` with:

```sh
export UV_CACHE_DIR=/tmp/hcmusec-lifecycle-uv-cache
export PYTHONPATH=/tmp
export DJANGO_SETTINGS_MODULE=hcmusec_lifecycle_settings
uv run python manage.py collectstatic --noinput
```

Select and record an available PostgreSQL port during setup; it is not a product
configuration. Browser tests replace DJANGO_SETTINGS_MODULE, so supply explicit
disposable `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` for them.
Store full logs and environment details under an ignored execution directory.
SQLite may help isolate pure behavior but cannot satisfy the final race gate.

## Task 1: Persist lifecycle state and authoritative provenance

**Files:** modify models; create `migrations/0006_competition_lifecycle.py`; extend
`tests/test_models.py` and `tests/test_migrations.py`.

**Interfaces:** produce nullable `Competition.ended_at`, `ended_stage` (Stage,
PROTECT) and `ended_champion` (CompetitionEntrant, PROTECT);
`CompetitionEntrant.removal_change` (nullable ChangeSet FK, PROTECT);
`Match.removal_effect` (private JSON, empty dict default);
`Round.availability_snapshot` (private JSON, empty dict default).

`removal_effect` stores `causes` (entrant ID plus original removal ChangeSet ID),
`before` and `applied` competitive match states. States include status, outcome,
winner, real scores, applied series and start/completion timestamps; scheduling
is not a competitive field. Scope and shape are server-validated, never editable
through model admin or accepted directly from requests. ChangeSet retains the
immutable copy. Repeated inactive-status relabelling keeps the original cause.

Round snapshots map string StageEntry IDs to entrant status, registration status
and selected state used at generation. They preserve historical inputs; later
publication also checks the actual eligible field. Old validated published Swiss
rounds use their original ACTIVE/APPROVED eligibility; preserve existing source
fingerprints. Private legacy previews still undergo current-field validation.
Do not invent removal provenance for legacy manually inactive entrants.

- [x] Add `test_lifecycle_upgrade_preserves_competition_history`: migrate a populated `0005_swiss` database, assert identical match/slot/tie/source-entry IDs and scores, unchanged publication/fingerprint history, nullable ending fields and empty removal provenance; restore the latest schema in cleanup.

  Core assertions after the populated migration:
  ```python
  assert after_history == before_history
  assert competition.ended_at is None
  assert match.removal_effect == {}
  assert entrant.removal_change_id is None
  ```
- [x] Add model tests for paired ended_at/ended_stage nullability, champion requiring an ending, protected references, and command-level rejection of foreign-competition stage/champion references (the latter lands in Task 5).
- [x] Run `uv run python manage.py test competitions.tests.test_models competitions.tests.test_migrations --noinput`; verify failures identify missing fields/migration.
- [x] Add fields, constraints and migration using historical migration models; backfill availability without rewriting scores, rule limits or provenance.
- [x] Rerun that command and `uv run python manage.py makemigrations --check --dry-run`; require passing tests and no model drift.
- [x] Commit only models, migration and these tests: `feat(competitions): persist lifecycle decisions and recovery provenance`.

## Task 2: Share elimination projection and availability-aware routing

**Files:** create `result_projection.py`, `tests/test_result_projection.py`;
modify `commands.py`; retain coverage in existing command/double-elimination/
stage-correction tests.

**Interfaces:** produce:

```python
def project_elimination_results(draw: StageDraw, *,
    result_updates: dict[int, dict], entrant_statuses: dict[int, str] | None = None) -> dict: ...
def apply_elimination_projection(draw: StageDraw, projection: dict) -> None: ...
```

Projection contains complete projected match states/slots plus changed match
IDs, public before/after impacts and reset-final changes. Status overrides are
keyed by CompetitionEntrant ID. Missing overrides use current status. Shared
ordered routing/reset/automatic-result primitives move with their callers if
necessary to avoid circular ownership. Do not keep two progression algorithms.

- [x] Add tests showing simultaneous changes to two source matches produce one coherent downstream projection; retain unaffected played branches and same-winner score changes, and reset exactly changed participants.
- [x] Add tests for withdrawn upper-bracket losers not entering the lower bracket, inactive historical winners not advancing again, both unavailable sides, pending unresolved opponents, structural byes and both reset-final policies. Assert prior entered finals remain unchanged.
- [x] Run `uv run python manage.py test competitions.tests.test_result_projection --noinput`; require behavior failures before implementation.
- [x] Generalize the current `_project_correction` logic into the shared functions. Route ordinary result correction and automatic progression through the same status-aware rules. A pending real two-player fixture uses forfeit/double-forfeit; an empty structural route uses existing bye/empty semantics. Never invent a bye while a source is unresolved.
- [x] Use projected complete competitive state when applying, including clearing/resetting applied series metadata only where required. Preserve actual partial scores for administrative forfeits. Task 4 attaches provenance to these effects within their owning command.
- [x] Run `uv run python manage.py test competitions.tests.test_result_projection competitions.tests.test_commands competitions.tests.test_double_elimination_commands competitions.tests.test_stage_corrections --noinput`; require all existing correction behavior plus new cases to pass.
- [x] Commit projection, callers and tests: `refactor(competitions): share result projection and availability routing`.

## Task 3: Preserve Swiss history while excluding unavailable entrants

**Files:** modify `swiss.py`, `swiss_commands.py`, `swiss_corrections.py`,
`qualification.py`, `round_robin_commands.py`, `handoff_commands.py`;
create `tests/test_lifecycle_swiss.py`; extend pure Swiss/qualification tests.

**Interfaces:** extend `pair_swiss_round(..., unavailable_entry_ids: Collection[int] = ()) -> SwissPairing`;
retain `rank_swiss` result accounting and W/L statuses. Extend
`stage_qualification(draw, *, projected_matches=None, entrant_statuses=None) -> dict`
and `group_standings(group, *, replacement=None, projected_matches=None, entrant_statuses=None) -> dict`,
plus `project_handoff_corrections(..., entrant_statuses=None) -> dict` with
CompetitionEntrant-ID status overrides. Return `earned_qualifier_entry_ids` and
eligible `qualifier_entry_ids` separately; retain the existing fingerprint,
cutoff and resolution-state fields. A shortfall returns BLOCKED with its reason.
For group state, keep `qualifiers` as the eligible list and add `earned_qualifiers`
and `block_reason`; stage aggregation must preserve a group's BLOCKED state.
Extend `project_swiss_correction(draw, *, projected_matches, entrant_statuses=None, retire_from_round=None) -> dict`
so restoration can name the earliest changed availability boundary while normal
score corrections keep using historical round snapshots. Pass the same projected
status map through ties, completion, handoffs and previews; GET uses current state.

- [x] Add pure tests: withdrawing one entrant from a five-entry Swiss field excludes that ID from pairs/byes, retains all five standings and opponent-point contributions, preserves saved seed folding and rematch rules, and leaves the frozen round limit unchanged.
- [x] Add persisted tests: removal after published round 2 leaves rounds 1–2 valid; invalidates a private round 3; regeneration excludes the entrant; later input-changing correction still retires the right suffix; an unavailable original registration no longer blocks active peers after explicit removal.
- [x] Add eligibility tests: a Top-2 earned qualifier removed from a four-entry field yields a one-person eligible set and BLOCKED handoff, never the third finisher; inactive cutoff contenders cannot win a new resolution; threshold completion ignores inactive continuers without changing their past W/L record.

  For an untied Top-2 result where the second finisher was removed:
  ```python
  assert state["earned_qualifier_entry_ids"] == [first.pk, second.pk]
  assert state["qualifier_entry_ids"] == [first.pk]
  assert state["qualification_state"] == "BLOCKED"
  assert third.pk not in state["qualifier_entry_ids"]
  ```
- [x] Run the focused tests to observe failures, then separate frozen field integrity/round-limit validation from present pairing/publication eligibility. Save round availability snapshots and use them for historical fingerprint comparisons; compare actual current availability for private previews.
- [x] Include current eligibility in qualification/handoff fingerprints. Do not treat status alone as a reason to replay every historical Swiss pairing. Restoration later supplies the earliest changed availability boundary explicitly.
- [x] Run `uv run python manage.py test competitions.tests.test_swiss competitions.tests.test_lifecycle_swiss competitions.tests.test_swiss_commands competitions.tests.test_swiss_corrections competitions.tests.test_swiss_handoffs competitions.tests.test_qualification competitions.tests.test_round_robin_ties --noinput`; require all old/new scenarios to pass.
- [x] Commit: `feat(competitions): continue Swiss and qualification after entrant removal`.

## Task 4: Signed withdrawal, disqualification and restoration commands

**Files:** create `lifecycle_commands.py`, `tests/test_entrant_lifecycle.py`;
modify `commands.py`, `command_support.py`, format projection call sites and
`tests/test_lifecycle_swiss.py` as needed for integration.

**Interfaces:** implement entrant preview/apply and `review_lifecycle_preview`
from the shared contracts. Consume Tasks 1–3. Produce auditable transition events
`entrant_withdrawn`, `entrant_disqualified`, `entrant_restored` and
`entrant_status_changed` (inactive label-only change).

- [x] Write preview/read-only and signed-apply tests across all five formats: pending and live fixtures, explicit consent, partial scores, existing finals, later draws, private drafts, invalid reasons/status/types, status relabelling, rejected stale/tampered/cross-object tokens and duplicate submission. Assert one revision/event per successful action and no changes on failure.
- [x] Write `test_restore_undoes_later_removal_forfeit`, `test_restore_preserves_manual_correction`, `test_two_removals_restore_in_either_order`, `test_restore_with_inactive_opponent_recomputes_forfeit`, and `test_restore_retains_historical_draws`. Assert before-state recovery, exact downstream reset set and immutable before/after history. Restore must reject an unapproved registration or missing removal provenance without partial writes.

  In the live-match fixture, start at a real 1–0 partial score before removal;
  after restoration with confirmed impact:
  ```python
  assert entrant.status == "ACTIVE"
  assert match.status == "LIVE"
  assert (match.side_one_score, match.side_two_score) == (1, 0)
  assert historical_forfeit["outcome"] == "FORFEIT"
  ```
- [x] Run `uv run python manage.py test competitions.tests.test_entrant_lifecycle competitions.tests.test_lifecycle_swiss --noinput`; require missing-command/behavior failures.
- [x] Implement read-only projections and signed tokens. Apply under the established locks, recompute impact and verify consent/permission before applying any effect. Record the event once, attach its removal reference, then commit together. Validate all payload fields and strict boolean consent at the command boundary.
- [x] Attach authoritative cause/before/applied provenance when removal or later normal result propagation creates an administrative result. Manual competitive correction invalidates that result's active automatic provenance, while its immutable ChangeSet history remains. Scheduling-only changes must not destroy restoration information.
- [x] Restoration reactivates the entrant, undoes only matching authoritative effects, and recomputes against all other current removals. List preserved manual corrections in the preview. Retire Swiss rounds generated after the changed availability boundary and invalid downstream draws; never revive superseded rows.
- [x] Reuse existing tie and handoff invalidation/application; preserve independent Round Robin fixtures and unaffected elimination branches. Make already-produced event payloads public only through Task 7's allowlist, with draft-only effects remaining private.
- [x] Run the focused lifecycle tests plus all existing result/stage/Swiss correction tests; require no regressions. Add a forced mid-apply failure test proving status, matches, provenance, history and revision roll back together.
- [x] Commit: `feat(competitions): withdraw and restore entrants with audited corrections`.

## Task 5: Exceptional endings, reopening and command-wide guards

**Files:** extend `lifecycle_commands.py`, `command_support.py`, all named
competition command modules; create `tests/test_competition_lifecycle.py`.

**Interfaces:** implement end/reopen preview/apply contracts. Add
`require_competition_open(competition: Competition) -> None` in command support
and invoke at every existing mutation boundary, including saved-preview reuse.
Reopening deliberately uses the underlying lock/revision checks without that
open-state guard. Read-only review may inspect ended state.

- [x] Test zero/one/multiple candidates, insufficient locked incoming fields, fixed/threshold Swiss impossibility, unresolved viable contests and ties. Assert only a determinable sole eligible survivor can receive an explicit competition award; otherwise only Without a champion is allowed. Reject foreign source/champion scope.
- [x] Test wholly private versus published/played suffixes; assert preserved rows, source scores, private visibility, frozen unfinished source contests and explicit reset permission/consent for published effects.
- [x] Test reopen clears the exceptional outcome, leaves entrant states/source scores unchanged and old suffix draws SUPERSEDED, and permits a fresh draw only after eligibility and locked-plan validation pass. Repeat end/reopen and stale-token submissions must not duplicate effects.
- [x] Run `uv run python manage.py test competitions.tests.test_competition_lifecycle --noinput`; observe failures, then implement ending feasibility from existing qualification/format rules. Do not use current row order as a champion or silently repair invalid rules.
- [x] Add the shared open-state guard to configuration/selection, draw save/publish, Swiss generation/publication, scheduling/start/progress/finalize, series edits, tie decisions, result correction and entrant transitions. Require a reopen before any ordinary mutation, including corrections to the source.
- [x] Add a table-driven test that calls each named mutation family directly against an ended competition; assert denial and identical state/revision/history. Reopening always requires both change permissions; ending a live source or published suffix requires both.
- [x] Run lifecycle tests and `uv run python manage.py test competitions.tests.test_stage_plan competitions.tests.test_handoffs competitions.tests.test_swiss_plan --noinput`; require passes.
- [x] Commit: `feat(competitions): end and reopen exceptional stage chains`.

## Task 6: Organizer lifecycle actions and impact confirmation

**Files:** modify `admin.py`, `admin_workspace.py`, `forms.py`,
`templates/admin/competitions/workspace.html`, `action_form.html`;
create `tests/test_lifecycle_workspace.py`; extend `tests/test_admin.py`.

**Interfaces:** forms call the seven lifecycle command functions. Add scoped
entrant transition, lifecycle preview/confirm, end and reopen URLs using existing
admin naming patterns; never write statuses/results directly from form handlers.

- [x] Add real admin GET/POST tests for Entrants actions, private reason, preview token, live-forfeit/reset checkboxes, stale feedback, current status and blocked-continuation explanation. Assert GET leaves revision/history unchanged and direct unauthorized URLs fail.
- [x] Add tests for view-only organizers, change_competition-only users, both permissions, non-organizer staff, inactive accounts and superusers; separately enforce private history permission. Test scope tampering and ended-state action visibility.
- [x] Run `uv run python manage.py test competitions.tests.test_lifecycle_workspace --noinput`; observe failures, then compose existing forms/action templates and Entrants workspace controls. Show every affected played result and preserved independent correction before final confirmation.
- [x] Reuse English organizer copy and accessible form/validation patterns. Label retired public stages and closed source contests without changing their recorded match outcomes. Reopen clearly explains replacement publication.
- [x] Run lifecycle workspace tests plus existing workspace/admin suites; require passing responses, command effects and permission boundaries.
- [x] Commit: `feat(admin): manage entrant removal and competition recovery`.

## Task 7: Public lifecycle state, history and bracket presentation

**Files:** modify `server/competitions/serializers.py`, `views.py`;
create `tests/test_lifecycle_api.py`; modify `web/src/lib/api/types.ts`,
`web/src/routes/tournaments/[slug]/games/[gameId]/bracket/+page.svelte`,
`web/messages/en.json`, `vi.json`, and existing bracket/API tests.

**Interfaces:** add entry `status` (ACTIVE/WITHDRAWN/DISQUALIFIED), competition
`ending` (null or `{stage_id, ended_at, champion}` with public entrant identity),
and stage `lifecycle_state` (OPEN/CLOSED/RETIRED). This is an additive public
contract; existing stage status, score and draw-state meanings stay intact.
Expose allowlisted lifecycle Changes with status transitions, match snapshots,
public retirement IDs and ending outcome. No private provenance structures.

- [x] Add API tests for availability separate from Swiss W/L status, explicit ended/no-champion/sole-survivor outcomes, retirement and reopened awaiting-replacement stages. Assert historical match URLs remain readable with original scores.
- [x] Add exact privacy assertions excluding private reasons, actor, private suffix/round IDs, removal references/snapshots and registration data, including nested Changes payloads. Assert all GETs are mutation-free and snapshots remain revision-consistent.
- [x] Run `uv run python manage.py test competitions.tests.test_lifecycle_api --noinput`; observe failures, then extend explicit serializers/querysets and existing published-history allowlists.
- [x] Add component/loader cases for availability labels, frozen source contests, retired stage navigation, reopening Changes and stable M-number links. Assert both locales and no new implicit polling/mutation behavior.
- [x] Extend existing API types and bracket presentation, reusing current components and translations. Keep historical outcomes separate from current availability; do not render provenance or internal blocking diagnostics to spectators.
- [x] Run API tests, then in `web/`: `pnpm exec vitest run src/routes/bracket-page.test.ts src/routes/bracket-page.svelte.spec.ts src/lib/api/competitions.test.ts`, `pnpm check`, `pnpm build`; require passes with existing third-party warnings reported separately.
- [x] Commit: `feat(web): show entrant availability and competition lifecycle history`.

## Task 8: Synthetic fixtures and complete browser journeys

**Files:** modify `registrations/dev_seed.py`,
`registrations/tests/test_seed_dev_data_command.py`, `e2e/fixtures.py`,
`e2e/serve.py`, `web/e2e/django/admin-bracket.spec.ts`, `bracket.spec.ts`.

**Interfaces:** extend existing development-seed and private browser fixture
contracts; create `dev-usec-lifecycle` synthetic tournament using real commands.
Include a restorable removal, an ended competition with played retired suffix,
and a reopened competition awaiting replacement. Use no workbook identities.

- [x] Add seed tests asserting lifecycle status/history, public/private fixture separation and identical IDs/results after rerun; preserve unrelated records and payment settings.
- [x] Run `uv run python manage.py test registrations.tests.test_seed_dev_data_command --noinput`; observe missing fixtures, then implement command-owned fixture creation without direct operational status overrides.
- [x] Add organizer browser journeys for withdrawal → preview → confirm → restore after downstream play, Swiss continuation after removal, and end → reopen → replacement preview/publication. Include stale confirmation and preservation of historical results.
- [x] Add spectator checks for status/outcome/history in EN/VI, historical match navigation, keyboard-accessible controls and `document.documentElement.scrollWidth === window.innerWidth` at 390px.
- [x] Run both complete bracket browser files with explicit disposable DB environment: `pnpm exec playwright test --config=playwright.django.config.ts e2e/django/admin-bracket.spec.ts e2e/django/bracket.spec.ts`; require every existing and added journey to pass.
- [x] Commit: `test(competitions): cover lifecycle fixtures and browser workflows`.

## Task 9: Concurrency, release gates and operating documentation

**Files:** extend `tests/test_concurrency.py`; create
`docs/testing/competition-lifecycle.md`; update `docs/BRACKET-TODO.md`,
`docs/TODO.md`, related operating-guide links and this plan's evidence.
If the earlier disposable benchmark script is unavailable, create
`server/competitions/benchmarks/swiss_publication.py` with the same persisted
256-entry/64-round case and cleanup/assertions, solely for repeatable proof.

**Interfaces:** reuse the PostgreSQL race harness with independent connections;
reuse production commands for timing. Record environment, commit/worktree,
commands, counts, skip status and logs. No new runtime service.

- [x] Add races for score versus removal, next-round publication versus removal, two restores, end versus score, end versus publication, duplicate reopen and registration eligibility versus lifecycle publication/restoration. Assert legal serialization, one winning revision, complete history and no mixed public snapshot.
- [x] Run `uv run python manage.py test competitions.tests.test_concurrency --noinput` on PostgreSQL with no skipped race tests. If a failure is scheduling-sensitive, establish a deterministic lock-wait barrier before changing production code.
- [x] Run the full competition/seed gate: `uv run python manage.py test competitions registrations.tests.test_seed_dev_data_command --noinput`; also run `registrations.tests.test_services`, `registrations.tests.test_reservation_concurrency` and `registrations.tests.test_admin_actions` to verify the shared division lock/eligibility boundary.
- [x] Run Django checks/migration drift, scoped Ruff, focused frontend tests/check/build and both full bracket browser files on the final code state. Reuse passing evidence only when later changes cannot affect that check, and state the exact scope.
- [x] Repeat persisted Swiss publication without competing tests/builds; record setup separately, SQL count, solver count/time and real publication time. Require one current-round solver call and no historical replay. Assert fixture/history correctness and remove only its disposable database afterward; no claim of worst-case production latency.
- [x] Document organizer actions, consent, privacy, current/historical semantics, restore conflicts, locked-plan blockers, migration recovery using matching code/database backups, test results and remaining limits. Reconcile V1–V5 item by item; do not close a gate merely because commands exist.
- [x] Review the complete branch, fix material findings, rerun affected checks and verify the final diff/status. Commit scoped tests/docs: `test(competitions): verify lifecycle integrity and document operation`.

### Task 9 verification evidence (2026-10-26)

From product source `b22d40f549c2ef031b00075f833e962f4a6a903d`, Task 9 adds
only tests, benchmark and documentation. Combined competition/seed/affected
registration gate: 486 passed in 754.657s; final PostgreSQL race file: 27 passed
in 19.148s, zero skips. Django checks/drift, scoped Ruff and frontend ESLint
passed. Unchanged frontend/browser evidence at that exact base remains applicable:
42 focused frontend tests, zero Svelte errors/warnings, successful build and
16 complete bracket browser journeys. Browser HMR/invalidation fetch errors
remain explicitly qualified in the operating guide.

The repeatable persisted 256-entry/64-round case measured 51.307509s publication,
238 SQL executions, one solver call (4.169810s), excluding 914.462635s fixture
setup. Historical state remained unchanged; own UUID database was removed.
This is local proof, not a production latency guarantee or controlled comparison
with the unavailable earlier script. See
[operating guide and V1–V5 reconciliation](../../testing/competition-lifecycle.md)
and the execution workspace's `task-9-report.md`/logs. Independent task review
approved the changes. The final whole-branch review of `95ed9eb..b8b811d` found
no Critical or Important issues and supported closing V1–V5 for the agreed
bracket-core scope. Its minor stale documentation references are corrected in
the final documentation commit. The browser console errors remain an explicitly
accepted verification limitation with unknown cause; production console behavior,
latency acceptance and a production backup restore were not verified.

### Completed task commits

| Task | Implementation and reviewed fixes |
| --- | --- |
| 1 — Persistence | `c517dbe` |
| 2 — Result projection | `fc123d5`, `009cd01` |
| 3 — Swiss availability and qualification | `122a976`, `068789d` |
| 4 — Removal and restoration | `e59031a`, `b97adde` |
| 5 — Ending, reopening and guards | `680dfb5`, `98acb45` |
| 6 — Organizer workflows | `f330e89`, `77583a0` |
| 7 — Public lifecycle and history | `6703316` |
| 8 — Fixtures and browser workflows | `b22d40f` |
| 9 — Concurrency, benchmark and operating proof | `b8b811d` |

The approved design/plan was committed as `81bfd6d`. Full reports, reviews and
logs remain in the ignored execution directory as required by the verification
plan. The branch remains `feat/tournament-brackets`; no merge, push or deployment
was performed.

## Plan self-review

- Persistence/upgrade and authoritative undo provenance: Tasks 1, 4 and 9.
- Prospective removal, all formats, global Swiss boundaries and earned qualifier shortfalls: Tasks 2–4.
- Ending feasibility, exact public/private retirement, reopening and mutation guards: Task 5.
- Organizer authorization/confirmation and public privacy/localization/accessibility: Tasks 6–8.
- Concurrent changes, fixtures, regression gates, performance and rollback documentation: Tasks 8–9.
- Each Review Focus item has explicit owning tests; no new data/scoring policy is inferred beyond the approved design.
- Public interfaces above are shared by later tasks; internal helper naming not specified here stays with the responsible implementer.
- Recommended execution: subagent-driven with sequential tasks and independent reviews, because projection/provenance errors can invalidate already-played results across multiple stages. Native execution remains available if the user prefers lower context overhead.
