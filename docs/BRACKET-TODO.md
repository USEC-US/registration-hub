# Bracket system core TODO

Updated: 2026-09-27. Branch: `feat/tournament-brackets`.

This is the authoritative competition-core backlog, linked from
[the project TODO](TODO.md#5-bracket-core). It replaces the scope and task list
in the [earlier competition delivery plan](superpowers/plans/2026-09-23-competition-formats.md).
The approved first single-elimination slice is implemented and focused-validated.
Its evidence and operating notes are in
[the single-elimination testing guide](testing/competition-single-elimination.md).
Double elimination is also implemented and focused-validated; see
[its testing guide](testing/competition-double-elimination.md). Round robin, Swiss,
and cross-stage behavior remain open below.

The delivered second slice is double elimination (E3/E4), including organizer and
public workflows. Its [implementation plan](superpowers/plans/2026-09-27-double-elimination.md)
was approved on 2026-09-27 for subagent execution and is now implemented.
The plan records sanitized
structural evidence from the supplied tournament workbook and distinguishes
historical single-elimination results from synthetic double-elimination
fixtures.

The approved foundation uses a dedicated `server/competitions` Django app.
The [detailed design](superpowers/specs/2026-09-23-competition-core-design.md)
and its initial defaults are approved. The
[first-slice implementation plan](superpowers/plans/2026-09-25-competition-core-single-elimination.md)
is approved.

## Agreed scope

- [x] Include single elimination, double elimination, single/double round robin
  groups, and Swiss, with qualification into elimination playoffs. TOs choose
  one or two meetings per pair for each round robin stage, independently of
  series length.
- [x] Support both Swiss presets: fixed rounds followed by Top-N qualification,
  and win/loss thresholds such as three wins to qualify or three losses to exit.
- [x] Support decisive best-of series and fixed-game series that can draw, such
  as Bo2 ending 1–1, for round robin and fixed-round Swiss.
- [x] Keep organizer controls in Django Unfold admin. Build new admin forms,
  templates, or components where existing ones do not cover the workflow.
  Public SvelteKit brackets, schedules, pairings, standings, and Changes are read-only.
- [x] Split implementation into small tasks with explicit dependencies and file
  ownership, so independent work can run through subagents in parallel.

Use organizer-selected approved registrations as entrants. Include manual
seeding, saved random draws, byes, private previews, publication, match IDs,
manual match scheduling, scores, advancement, correction, and audit history.
The Garena screenshot is a workflow reference; use this site's existing visual
system and accessible mobile presentation.

TFT lobbies, placement points, and Checkmate remain outside this phase. Live
push updates belong to project Section 6; this core must work through normal
HTTP first. Registration/payment changes and participant result submission
are outside this backlog.

### Confirmed series configuration

- [x] Configure a default series length for each stage.
- [x] Allow round overrides and individual-match overrides before the relevant
  match starts; resolve the length as match override → round override → stage
  default.
- [x] Keep the applied series length stable once a match starts. Overrides must
  remain valid for the selected series mode and competition format.

Admin and public match views must display the same effective series length.
These are confirmed requirements, not completed implementation tasks.

### Confirmed stage structure

- [x] Allow an ordered sequence of stages within a division, using the supported
  formats. A division may also have a single standalone stage.
- [x] Let TOs confirm advancement between stages, including groups → another
  qualifying stage → playoffs. Handoffs are not limited to a single qualifying
  stage followed by an elimination bracket.

Keep entrant identities and registration snapshots consistent across stages.
Each handoff must validate the destination's entrant requirements and retain
its source qualifiers. Correction impact previews must follow those handoffs
when a result change affects a later stage, including matches already played.

### Confirmed correction behavior

- [x] Allow a TO to correct a winner even after dependent matches have been played.
- [x] Show the affected matches, pairings, and progression in an impact preview;
  require explicit confirmation before resetting affected downstream results.
- [x] Preserve superseded results and reset history in a read-only **Changes**
  view. Resetting current competition state must not erase the earlier results.
- [x] Make result changes public, while keeping TO identities and internal notes
  private. Authorized organizers can inspect the full audit record in admin.

Public Changes shows published result changes and resets: affected matches,
timestamps, and previous/new public scores and outcomes. Draft history, actor
identity, internal notes, and private registration data are excluded from the
public response itself, not merely hidden by the interface.
These are confirmed requirements, not completed implementation tasks.

### Confirmed qualification tie resolution

- [x] When the configured tiebreakers leave a tie affecting qualification, let
  the TO choose extra tiebreak matches or a recorded manual decision.
- [x] Keep the affected qualification unresolved until that choice produces a
  confirmed outcome. Do not silently choose an entrant by database ID, display
  order, or a random draw.

Preserve the resolution and resulting qualifier changes in Changes, with TO
identity and internal notes restricted to the organizer view. Extra tiebreak
matches use the shared match/result lifecycle, including correction history.
The exact rules for resolving a tie among three or more entrants are defined by
the approved R3/R4 design.

### Confirmed Swiss exceptions

- [x] If no complete no-rematch pairing exists, allow an explicit, recorded TO
  override for required rematches. Never silently relax opponent-repeat rules.
- [x] Count a Swiss bye as a normal match win, including when it reaches the
  qualification threshold. Label it as a bye without fabricating played scores.

## 0. Settle the rules and design

Complete the decisions needed by a task before releasing that task to an agent.
Capture the outcomes in a focused rules/design document, then produce the
implementation plan. Do not treat the choices below as already implemented.

- [x] **R1 — Stage and entrant lifecycle.** Apply the confirmed ordered-stage
  structure and TO-confirmed handoffs. Define entrant limits, team/solo public
  labels, selection of approved registrations,
  roster identity preservation, withdrawals/disqualification, and what happens
  if an entrant's eligibility changes after selection or publication.
- [x] **R2 — Series and result rules.** Apply the confirmed stage/round/match
  series-length precedence and before-play restriction. Define valid/in-progress/
  final scores, draws, forfeits, double forfeits, and walkovers. Define what counts
  as a match win versus an individual game win, and how a match is marked started.
  Elimination and threshold Swiss need an explicit decisive-result rule.
- [x] **R3 — Elimination and group rules.** Confirm bye placement, bracket
  seeding, double-elimination routing, and the grand-final reset/no-reset choice
  before publication. Apply the confirmed single/double round robin choice;
  define group sizes, points, and ordered tiebreaks. Apply the confirmed extra-match
  or recorded-decision resolution for remaining qualification ties, including
  rules for three or more tied entrants.
- [x] **R4 — Both Swiss presets.** Define pairing order, score groups, rematches,
  byes, withdrawals, impossible pairings, and validated manual overrides. Define
  fixed-round standings/tiebreaks and threshold exit/completion rules, including
  which finishers advance and how the next stage's seeds are determined. Apply the
  confirmed qualification-tie resolution paths, forced-rematch override, and
  normal-win bye credit, including qualification.
- [x] **R5 — Publication, correction, and handoff.** Define draft/public states,
  publication locks, and stale-edit handling. Apply the confirmed impact-preview,
  downstream-reset, and public/private Changes-history policy. Define how a TO
  confirms qualifiers and starts the next stage. Publication locks must allow
  the agreed series-length overrides before play. Review the written design and
  implementation plan before product code begins.

## 1. Shared foundation — one integration owner

These tasks establish the contracts used by every format and surface. One owner
controls migrations, shared types, command signatures, and integration wiring.
The approved implementation home is `server/competitions`; retain the existing
tournament/division and registration ownership. The implementation plan assigns
exact module boundaries and owned files after the written design is reviewed.

| ID | Task | Depends on |
| --- | --- | --- |
| C1 | [x] Implement the competitions app's competition root, ordered stages, saved draw versions, entrant identity, constraints, snapshots, and additive migrations, with model tests. | R1, approved design/plan |
| C2 | [x] Define and implement the shared match/result lifecycle, series-length precedence and locking, scoring validation, transaction boundaries, revision checks, and attributable result history. | C1, R2, R5 |
| C3 | [x] Implement private preview and publication validation, including entrant eligibility and locked published rules. | C1, C2, R5 |
| C4 | [x] Define and implement the first-slice allowlisted public bracket, schedule, match, and Changes responses and admin command inputs/results. Later-format standings and pairings remain with their format tasks. | C1–C3 |
| C5 | [x] Implement correction impact previews and atomic correction/reset commands, including already-played single-elimination dependents; retain superseded results and reset events for Changes. Cross-stage resets remain with H1. | C2, R5, relevant format dependency rules |

Reuse current `TournamentGame` divisions and registration snapshots. Public
competition responses need their own explicit field allowlist: the existing
owner-facing registration response includes payment and private receipt data.
Current tournament API routes and tests provide the public-read pattern.

## 2. Format tasks

Each task owns its format logic and focused tests. Use agreed inputs/outputs;
format agents do not independently redesign models, result commands, or APIs.
Pure generation/pairing/calculation work can run concurrently once its contract
and rules are fixed. Persisted integration follows the shared command path.

| ID | Task | Depends on |
| --- | --- | --- |
| E1 | [x] Generate and preview single-elimination draws from manual seeds or a saved random draw, including uneven fields and byes. | C1, C2, R3 |
| E2 | [x] Advance single-elimination winners, handle the first-slice played, forfeit, double-forfeit, bye, and empty outcomes, and complete the final. Withdrawal/disqualification flows remain a later slice. | E1 |
| E3 | [x] Generate double-elimination upper/lower routes and verify loser destinations for small and uneven fields. | E1, C2, R3 |
| E4 | [x] Advance both brackets and implement the approved grand-final reset/no-reset policies and completion. | E2, E3 |
| G1 | [ ] Assign round robin groups and generate the chosen single/double schedule, including odd-sized groups; each pair meets exactly once or twice independently of series length. | C1, C2, R3 |
| G2 | [ ] Calculate group standings, points, ordered tiebreaks, and provisional qualifiers from confirmed results. | G1, R2, R3 |
| S1 | [ ] Generate and preview one Swiss round using the agreed pairing rules, normal-win bye handling, and explicit recorded overrides for unavoidable rematches. | C1, C2, R4 |
| S2 | [ ] Implement fixed-round Swiss progression, standings/tiebreaks, and provisional Top-N qualifiers. | S1, R2, R4 |
| S3 | [ ] Implement threshold Swiss progression, qualification/elimination, and stage completion. | S1, R2, R4 |
| H1 | [ ] Preview and confirm qualifiers/seeds entering the next stage of any supported format; validate destination capacity/rules, block unresolved qualification ties, and reject duplicate/cross-division entrants. | C3, C5, applicable source progression/standings and destination setup, H2 when tied |
| H2 | [ ] Resolve qualification ties through TO-selected extra tiebreak matches or a recorded manual decision; validate tied entrants and available places, preserve history, and recompute when source results change. | C2, C5, R3/R4 tie rules, relevant G2/S2/S3 source |

## 3. Django Unfold organizer tasks

Reuse `OrganizerStaffAdmin`, existing model permissions, guarded service
commands, and the registration admin's confirmation-form and CSRF-protected POST
patterns. Keep direct status/result edits from bypassing the commands. New UI
components should cover a concrete workflow, with separate file ownership where
agents work concurrently.

| ID | Task | Depends on |
| --- | --- | --- |
| A1 | [x] Extend least-privilege organizer permissions/bootstrap and test view/change boundaries, non-organizer staff, inactive users, and superusers. | C1, C2 |
| A2 | [x] Build single/double-elimination competition/stage setup, approved-entrant selection, stage series defaults, and round overrides. | C3, C4, A1 |
| A3 | [x] Build manual single/double-elimination seeding, saved random draw, private preview, and explicit publication controls. Group assignment remains with G1. | A2, relevant E1/E3/G1/S1 generators |
| A4 | [x] Build match-list/detail scheduling, individual series-length overrides before play, and score-entry actions with clear validation and stale-edit feedback. | C2, C4, A1, relevant format progression |
| A5 | [x] Build correction impact/confirmation screens and the full organizer Changes view, including previous results, downstream reset history, actor, timestamp, and internal reason. | C5, A4 |
| A6 | [ ] Build standings, Swiss next-round controls, qualifier previews, and confirmed handoffs between ordered stages. | applicable source progression/standings, H1, A1 |
| A7 | [ ] Build qualification-tie resolution controls: schedule extra tiebreak matches or record a manual decision, with confirmation, validation, and Changes history. | H2, A1, A4, A5 |

One integration owner wires admin modules, URLs, navigation, and shared templates.
Other agents own specific forms/views/templates and their tests. Add no reusable
admin framework merely to make these tasks look uniform.

## 4. Public read-only tasks

| ID | Task | Depends on |
| --- | --- | --- |
| P1 | [x] Implement published-only first-slice competition snapshots and privacy tests using the agreed allowlist. | C3, C4, relevant format readers |
| P2 | [x] Build accessible single/double-elimination bracket views with match IDs, schedules, effective series lengths, scores, winners, and mobile navigation. Includes upper/lower/finals sections and conditional/not-required reset states. | C4 fixtures; connect to P1 before completion |
| P3 | [ ] Build round robin/Swiss standings, round pairings with effective series lengths, stage navigation, and qualification states. | C4 fixtures; connect to P1 before completion |
| P4 | [x] Connect single/double-elimination pages to the real API; handle unpublished/missing, ready/live/completed, refresh, time zones, and EN/VI UI. Later-format states remain with P3. | P1–P3 |
| P5 | [x] Expose and render read-only public Changes for published result revisions and resets; test before/after outcomes and exclusion of actor identities, internal notes, and draft history. | C4, C5, P1 |

Reuse existing SvelteKit public loaders, API client, localization, time-zone
formatters, and visual components. Public screens must never receive contact
details, real names, birth dates, student IDs, payment data, credentials, or
private organizer history through API responses or page data.

## 5. Parallel execution and acceptance

### Dispatch rules

1. Finish the applicable rules and shared contracts before dependent code starts.
2. Give each subagent one task with its accepted behavior, exact owned files,
   prerequisites, and a focused verification command. Split any task that spans
   multiple independently testable behaviors before dispatch.
3. Run independent format work, admin screens, and public components concurrently
   when their contracts are available. Shared-file edits and migration creation
   stay with the integration owner; agents request changes to those contracts.
4. Integrate a complete usable single-elimination workflow first. Add double
   elimination, groups, and both Swiss presets as independently verified slices;
   preparatory work for later slices can proceed in parallel.
5. Verify the assembled flow before marking a task complete. An algorithm or a
   mocked screen alone does not complete its backend-to-UI workflow.

### Completion checks

- [ ] **V1 — Format behavior:** small/uneven fields, byes, draws where allowed,
  invalid scores, forfeits, withdrawals, both grand-final policies, both Swiss
  presets, both round robin schedules, ties, pairing limits, and confirmed playoff
  qualification. Verify round robin meeting counts independently of series length,
  series-length precedence, rejection of edits after play starts, and consistent
  effective lengths in admin and public views. Verify extra-match and manual
  qualification-tie resolution, including multi-entrant ties and source-result
  corrections that invalidate an earlier resolution. Include forced-rematch
  overrides, qualification by bye, and the design's exceptional completion paths.
- [ ] **V2 — Mutation integrity:** PostgreSQL tests cover concurrent result
  entry, stale previews, repeated actions, transactional rollback, and correction
  through downstream matches/pairings/stage handoffs. Include already-played
  dependents and sequences of more than two stages; verify prior results remain
  available in Changes after a reset.
- [ ] **V3 — Permissions/privacy:** direct requests cannot bypass organizer/model
  permissions or published-only visibility; public responses use only approved
  display fields, including in Changes history; actor identities and internal
  notes stay private; GET requests do not mutate competition state.
- [ ] **V4 — Full workflow:** real Django/admin/Svelte browser journeys cover
  setup → entrants → seed/assign → preview → publish → schedule → results →
  correction → qualification/completion. Verify mobile, keyboard access, and
  English/Vietnamese presentation and public versus organizer Changes views.
  Keep registration behavior working.
- [ ] **V5 — Delivery:** provide realistic dev/test fixtures, organizer operating
  notes, migration/rollback guidance, and recorded check results. Update this
  checklist and the project TODO with actual completion and remaining limits.

First-slice evidence now covers the single-elimination portions of every gate:
deterministic uneven draws and result rules for V1; PostgreSQL revision,
finalization, correction, and publication races for V2; permission and public
allowlist checks for V3; Django admin integration plus a real localized,
responsive public browser journey for V4; and repeatable fixtures, operating
notes, migration guidance, and recorded results for V5. The V1–V5 gates remain
open because their text also requires later formats, ordered-stage handoffs, and
a complete organizer browser journey.

Core is complete when an authorized TO can run all agreed formats and ordered
stage handoffs through Django Unfold admin, and spectators can follow published
schedules, results, standings, and progression. Realtime and Full Beta hardening
retain their separate project gates.
