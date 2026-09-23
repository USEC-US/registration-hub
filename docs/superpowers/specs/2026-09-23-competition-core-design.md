# Competition core design

Date: 2026-09-23. Branch: `feat/tournament-brackets`.

Status: **Draft for written review.** The user approved the shared foundation
and the decisions listed below. The remaining concrete defaults in this document
are proposals for that review; they are not implemented behavior.

Work tracking: [Bracket core TODO](../../BRACKET-TODO.md).
This design supersedes the scope of the earlier
[competition delivery plan](../plans/2026-09-23-competition-formats.md).

## 1. Outcome and review guide

A tournament organizer can run a division from approved registrations through
one or more competition stages, operate its matches in Django Unfold admin,
correct mistakes safely, and publish brackets, standings, schedules, and Changes
to spectators. The Garena reference establishes the match-operation workflow;
the implementation uses the site's existing visual system.

The user has selected:

- A dedicated `competitions` Django app, sharing a common competition core.
- Single/double elimination, single/double round robin groups, and both Swiss
  presets: fixed rounds with Top-N qualification and win/loss thresholds.
- Ordered stage chains with explicit TO confirmation of advancement; both
  decisive best-of and fixed-game series with draws where the format permits.
- Stage series-length defaults, round overrides, and match overrides before
  the relevant match starts.
- Corrections after downstream play, with impact previews and explicit resets;
  public Changes preserves history while TO identities/internal notes stay private.

Further agreed rules: qualification ties may use extra tiebreak matches or a
recorded manual decision. A forced Swiss rematch requires an explicit recorded TO
override. Swiss byes count as normal match wins, including reaching qualification.
TOs work in Unfold; public SvelteKit views are read-only. Work is divided into
small tasks with explicit ownership for parallel subagents.

**Read these proposed defaults before approving the specification:**

1. Points and supported tiebreaks are configured before publication. Default
   points are win 3 / draw 1 / loss 0; exact ranking rules are in Sections 7–8.
2. A withdrawal preserves earlier results and resolves remaining published
   fixtures as forfeits. Disqualification uses the same mechanics; retroactively
   voiding an earlier result requires the correction workflow.
3. Extra tiebreaks use a decisive match for two entrants, or a small single
   round robin for a larger tied set. A remaining tie requires another explicit
   resolution; it never silently falls back to seeding.
4. Publication locks the field, format, standings rules, and qualification
   policy. Scheduling and valid series-length overrides remain editable before
   the affected match starts.
5. Initial supported bounds are 2–256 entrants per stage, at most 16,384 regular
   generated matches per draw, and at most 64 Swiss rounds. These are explicit
   server validation limits, not changes to registration capacity. Larger fields
   require measured validation before raising the limits.
6. Exceptional results can leave no champion. If a stage chain cannot continue,
   the TO may explicitly end it and retire its remaining stages after an impact
   preview, preserving published results and history (Sections 6 and 9).

TFT, live push transport, participant score submission, automated scheduling,
game-provider integrations, and registration/payment redesign are outside this
core. Existing HTTP behavior must remain sufficient when realtime is added later.

## 2. Ownership and existing integration points

`tournaments` continues owning `Game`, `Tournament`, and `TournamentGame`.
`registrations` continues owning eligibility, payment review, and immutable
registration/roster snapshots. `competitions` owns competition state and commands.

Use the existing `TournamentGame` as the division identity and existing approved
registrations as the entrant source. Do not create another team/account system.
Use `OrganizerStaffAdmin` and the registration admin's guarded action/form
patterns. Extend `bootstrap_organizers` after the new permissions exist. The
current `config.permissions` module guards API documentation; it is not an
organizer authorization helper.

The alternative was to extend `tournaments`. The chosen app boundary adds normal
Django wiring but gives the competition lifecycle and parallel task owners a
clear home. Format modules are ordinary Python calculations, not a plugin system.
They return draws, pairings, progression effects, or standings; shared commands
validate and persist those results.

```text
TournamentGame
  └─ Competition (entrant pool, revision, command boundary)
       └─ ordered Stages
            └─ saved Draw versions
                 ├─ StageEntries and optional round robin Groups
                 └─ Rounds → Matches → two Slots

Unfold forms → competition commands → transaction + Changes
                                     ↓
                         allowlisted public read API → SvelteKit
```

Use Python/Django for generation and scoring, browser HTML/CSS/SVG for bracket
presentation, and existing Svelte components/localization/time formatting.
The proposed additional algorithm dependency is NetworkX for general graph
matching in Swiss. A maintained matching implementation avoids owning blossom
or exponential backtracking code. Add it during Swiss implementation, lock its
version, and verify its API/license and deterministic fixtures then. No matching
dependency is needed for the first single-elimination release.

## 3. Persisted state

Names below define ownership; the implementation plan will assign exact fields,
migration files, and task owners. Relational identifiers and lifecycle state use
typed fields. Validated JSON is limited to ordered tiebreak options, immutable
command snapshots, and public/private history payloads.

| Record | Responsibility and constraints |
| --- | --- |
| `Competition` | One-to-one with `TournamentGame`; monotonically increasing revision; root for entrant selection and commands. Its own row keeps competition revision state out of catalogue models. |
| `CompetitionEntrant` | Unique registration within a competition; immutable registration linkage and public display snapshot; active/withdrawn/disqualified state. Registration deletion is protected. |
| `Stage` | Unique active sequence position within a competition; name, format, format rules, series mode/default length, scoring/tiebreak/qualification policy, and first-publication timestamp. |
| `StageDraw` | One current draw per stage, with numbered retained versions; draft/published/superseded state. Saves exact entrant ordering/group assignment. A later-stage draw records its source draw, qualifying input fingerprint, and confirmation. |
| `StageEntry` | Unique competition entrant within a draw; seed and group; original source entry for advancement where applicable. Stage losses/qualification come from confirmed results, not account state. |
| `StageGroup` | Round robin group name/order, membership through StageEntry, and number of qualifying places. Minimum two entrants; all members belong to the same draw. |
| `Round` | Draw, optional group, section (upper/lower/final/normal/tiebreak), ordinal, series-length override, generation, publication/supersession state, and saved generation-input fingerprint for Swiss. |
| `Match` | Stable ID and public match code; round, schedule, lifecycle, series-length override/applied length, current scores, outcome, winner where applicable, and started/completed timestamps. |
| `MatchSlot` | Exactly two positions per match. Holds a direct entry or a winner/loser source match, resolved entry, and whether its source is resolved. Unknown entrants and known empty slots are different states. |
| `TieResolution` | Draw/group, tied set, required places, source fingerprint, method, optional tiebreak round(s), and confirmed ordering/selection. Preserve superseded resolutions. |
| `ChangeSet` | One committed command/revision, actor, timestamp, internal reason, affected records, exact private before/after state, and separately constructed public changes. Read-only after creation. |

Generated match, draw, entry, and history rows are not directly editable through
generic admin forms. Commands enforce same-competition/draw references and
exactly two slots; database constraints enforce unique positions, sequence
identity, current versions, and nonnegative scores. Do not rely on `save()`
calling `full_clean()`. Protect retained records from cascading deletion.

Current state is the operational projection; ChangeSet is history, not an event
sourcing engine. A result correction usually updates current matches and saves
before/after history. Replacing an invalidated stage draw or Swiss round keeps
the old rows as superseded and assigns new IDs to replacement matches. Stable
IDs of unchanged matches do not change.

### Entrant identity and eligibility

Select only `APPROVED` registrations from the same division. Check again when
publishing the first draw and confirming a later-stage handoff, under the division
lock. Team display uses the saved team name/tag; solo display uses the main
player's saved gamer tag. Any displayed roster gamer tags/school labels come
from existing snapshots. Private name, birth-date, student-ID, contact, account,
and payment fields are never copied into the public entrant representation.

Freeze the competition display identity when first published. A later profile
edit cannot rename old matches. A registration eligibility change must not
silently remove or rewrite a published entrant: surface it to the TO, block new
publication/advancement for that entrant, and require a withdrawal/disqualification
decision. Existing scores remain until an explicit correction changes them.

## 4. Drafts, publication, and ordered stages

Setup creates a private draft. Manual seeding and randomization are POST commands.
Randomization saves the exact permutation using a system random source; refresh
and publication reuse that saved draw. No GET request creates or shuffles data.

Before publication validate eligible unique entrants, required seeds/groups,
format settings, series/scoring rules, qualification capacity, generated match
budget, and acyclic winner/loser dependencies. Preview displays real saved
fixtures, byes, rules, and qualification policy. Publish the reviewed draw in one
transaction; later edits cannot silently redraw it.

Stage presentation states are derived from publication/current draw:

- **Draft:** private setup/fixtures.
- **Ready:** published draw with no started match.
- **In progress:** at least one started match and required play remains.
- **Awaiting resolution/advancement:** ordinary play finished but qualification
  or required placement ties remain, or a replacement draw needs confirmation.
- **Complete:** required results and placement/qualification decisions are final.

Publishing a later stage requires a confirmed handoff from the preceding active
stage and a valid destination draw. Only the first stage selects from the
registration pool. Later stages consume confirmed source qualifiers; they do
not introduce unregistered entrants or reopen registration. A division can have
one standalone stage or a longer ordered chain. Branching stage graphs and
merging fields from other divisions are outside this version.

The TO configures qualification policy before source publication: Top-N for an
overall stage, per-group place counts for round robin, or the complete set of
threshold-qualified entrants for threshold Swiss. A final stage also defines
the placement cutoff it must resolve, defaulting to a sole champion.

Source qualifiers must fit the destination's supported field and group rules.
Threshold Swiss qualifies whoever reaches its win target; do not silently trim
that set to a presumed Top-N. Destination size follows the confirmed qualified
set. If too few eligible entrants remain to start the destination, advancement
is blocked with an explicit explanation and the end-chain path in Section 9.
Changing a published qualification
rule requires a separately reviewed future feature, not an ad hoc form edit.

Draft suffix stages can be added/reordered while preserving the order and
dependencies of published stages. Published stages cannot return to private
draft status or be deleted. Unpublishing the parent tournament uses the existing
catalogue visibility control and hides all its public competition endpoints.

## 5. Series rules and match operation

Each ordinary stage chooses a series mode before publication:

| Mode | Validation and completion |
| --- | --- |
| Best-of N | N is positive and odd. First to `(N + 1) / 2` game wins wins the match. A final score has exactly one side at that threshold and the other below it. |
| Fixed N games | N is positive. A completed series has scores summing to N; a tie is a draw. Permitted only in round robin and fixed-round Swiss. Individual-game draws are outside this version. |

Effective length is match override, otherwise round override, otherwise stage
default. An override changes length within the selected series mode and must
remain valid for that mode/format. Tiebreak contests have their own decisive
best-of setting, default Bo1, even if ordinary group play uses fixed-game series.

Before a match starts, the TO can edit its length or schedule. A stage/round
default edit is rejected if it would change the applied length of any started
match that inherits it. Unstarted matches can still receive explicit overrides.
Store the applied mode/length when a match starts so future configuration cannot
reinterpret its scores.

The TO can use **Start match**, **Save progress**, or **Finalize result**.
Saving the first progress/final result also starts the match if necessary and
captures its series settings. Scheduled time alone does not mark a match started.
Both slots must be resolved and eligible before ordinary play starts. Live scores
must be nonnegative integers within the series bounds. A terminal score requires
finalization; finalization and advancement happen atomically. Standings use
confirmed final results, while public match views can show saved live scores.

| Outcome | Competition meaning |
| --- | --- |
| Played win/draw | Use validated series scores; draws only where allowed. |
| Forfeit | Name the winning side; the other side loses. Preserve any actual partial scores, but do not fabricate a 2–0/3–0 score. |
| Double forfeit | No winner. Both sides receive losses and zero points. In elimination, administratively eliminate both sides and resolve both winner and loser routes empty; in threshold Swiss each receives one loss and the usual threshold rule applies. |
| Elimination bye | Auto-advance the sole eligible side only when both source slots are resolved; no game scores or fictitious loser. |
| Swiss bye | One normal match win/normal win points, no games played and no opponent; it can satisfy the qualification target. |
| Empty structural match | Both resolved slots are empty; resolve both outgoing sources empty. This is not a played match or a scored draw. |

Forfeit/double-forfeit/bye outcomes contribute no fabricated game wins or game
difference to tiebreaks. Recorded partial scores remain visible as partial
play, but game-based standings metrics include only completed played series.
Round robin rests caused by an odd group size are not wins and award no points.

In double elimination, a double forfeit cannot send two losers into one lower
slot. Both entrants leave the stage by administrative double-forfeit outcome,
not by inventing a second played loss, and cannot qualify from that stage.
The confirmation must state that effect.
If a final or fully empty final path has no surviving winner, explicitly complete
the stage with **No champion**; do not pick a seed or leave an impossible contest
waiting forever. Ordinary draws and ranking ties still use tie resolution.

Withdrawal/disqualification blocks future entry/advancement. It preserves prior
results and resolves already published unplayed fixtures as forfeits; when both
sides are unavailable, use double forfeit. A live fixture needs an explicit
confirmed forfeit decision. Swiss excludes withdrawn entrants from new rounds.
The decision and its effects are audited. Restoring a withdrawn entrant after
results/pairings depend on the withdrawal uses correction preview/reset rules.

## 6. Elimination generation and progression

### Single elimination

Use the smallest power-of-two field containing the entrants. Seed 1 is strongest.
Build the standard seed order recursively: starting `[1, 2]`, expand each seed
`s` to `[s, new_field_size + 1 - s]`. Eight slots are
`[1, 8, 4, 5, 2, 7, 3, 6]`. Missing seeds are known empty slots, granting byes to
the higher seeds. Manual seed order and a saved randomized order use the same
generator.

The winner of each match feeds its fixed next-round slot. Unknown sources never
count as byes. Resolve structural empty/bye paths transitively without recording
fictional played scores. Finalization advances once; a correction follows the
same dependency graph under the correction command.

Placement uses elimination depth; entrants losing in the same round remain tied
unless a required cutoff invokes TieResolution. There is no automatic third-place
match. A TO can resolve a required third-place cutoff using the agreed tiebreak
workflow.

### Double elimination

Use the same seeded upper bracket. A played upper loss routes to the lower
bracket; a lower loss eliminates. Structural byes produce no losing entrant.
For a padded field `N = 2^k` with `N >= 4`:

1. Lower round 1 pairs losers of adjacent upper-round-1 matches.
2. For each upper round r from 2 through k, create a lower drop round that pairs
   the surviving lower entrants with that upper round's losers in reversed
   match-index order. This is the saved canonical routing, not a dynamic redraw.
3. Between consecutive drop rounds, merge adjacent lower winners to halve the
   field. There are `2k - 2` lower rounds.
4. The upper winner meets the lower winner in the grand final. For N=2, the upper
   loser goes directly to that final; there is no separate lower contest.

The TO chooses **reset** or **no reset** before publication; the public bracket
states the rule. With reset, an upper-winner loss activates the reserved reset
final; otherwise that conditional match is not played. With no reset, the first
grand final decides the champion even if it is the upper entrant's first loss.
Do not add an undeclared game advantage. A reset triggered/removed by correction
is included in the impact preview and history.

Publish exact routing fixtures for 2/4/8/16 entrants as algorithm tests, then
exercise uneven fields and larger powers of two. Assert no entrant is both
active twice in a round, loss routes are acyclic, and every real played loser
has the correct next destination. Rematches are legitimate in double elimination.

## 7. Round robin groups and standings

TOs choose single or double round robin per stage, independently of series
length. Save group membership before publication. Support manual allocation or
seeded snake allocation across the configured group order. Every group has at
least two entrants; groups may differ in size by manual configuration if valid.

Generate each group's schedule with the circle method: keep one position fixed,
rotate the rest, and pair opposite positions. Append one empty position for odd
group sizes and display the corresponding rest. For double round robin, append
the same cycle with reversed side positions. Every unordered pair appears
exactly once/twice; an entrant plays at most once in a group's ordinary round.

Points are stage-configurable nonnegative decimals with two fractional digits:
`win > draw >= loss`. Default is 3/1/0. Forfeits use normal win/loss points;
double forfeits award zero to both. Byes/rests create no round robin points.

After primary match points, the TO selects an ordered, nonrepeating subset of
supported tiebreaks: head-to-head points, match wins, game difference, games won.
Default order: head-to-head points → game difference → games won. Rules are
published and locked before play.

Head-to-head evaluates the mini-table among the entrants still tied at that
criterion, using confirmed meetings in the current draw. Do not recursively
restart the same criterion after a subgroup separates; continue to the next
configured criterion. Game metrics include completed played series only.

Equal ranks remain equal after all configured criteria. Seed/name may stabilize
display order but cannot award a place. A tie affecting the configured qualifying
or required placement cutoff blocks its confirmation until resolved.

## 8. Swiss presets and pairing

Both presets use the shared match/results model and one published round at a
time. The current round must have final outcomes for every eligible entrant
before the next round is generated. Each generation saves its input fingerprint
and exact pairing; refresh does not rerun the solver.

### Standings and termination

**Fixed rounds:** configure round count, points, ordered tiebreaks, and Top-N
qualification before publication. Fixed-game draws are allowed. Default points
are 3/1/0. Default tiebreaks are opponent points → game difference → games won;
match wins is an additional supported configurable criterion.

Opponent points is the sum of the current confirmed match points of opponents
actually assigned in prior rounds, counting each meeting, including forfeits.
Repeated meetings count repeatedly. Byes contribute no opponent. Withdrawn
opponents retain their earned points. This is the advertised esports preset;
do not label it as implementing a federation's adjusted Buchholz rules.

**Win/loss thresholds:** configure positive W and L targets. Matches must be
decisive best-of series. Match wins/losses, not individual game wins, drive exits.
An entrant reaching W qualifies; one reaching L is eliminated. Withdrawn entrants
exit without qualifying. Byes count as wins, including the qualifying win;
double forfeits count as losses for both sides. Every active entrant receives
one outcome each round, so the stage ends within `W + L - 1` rounds. Validate that
bound against the supported round limit before publication.

All threshold-qualified entrants advance, subject to eligibility and explicit
TO handoff. Proposed seed order is match wins descending, losses ascending, then
opponent match wins descending. Bye games have no opponent for that sum. Any
remaining seed-order tie must be explicitly confirmed by the TO; it is not
silently resolved by database ID. Elimination in this preset does not re-enter
an entrant in a later Swiss round.

### Pairing contract

First round: use the saved seed/random order; if odd, the last seed receives the
bye. Split the remainder into upper/lower halves and pair matching positions.

For subsequent rounds, compute a complete matching over eligible active entrants.
Fixed mode groups by match points; threshold mode groups by win/loss record.
Use integer costs and stable node/edge insertion order with the locked matching
dependency. Minimize priorities lexicographically:

1. Prior bye count of the selected bye recipient, then prefer the lowest-ranked
   eligible recipient; a dummy vertex models an odd-field bye.
2. Number of cross-score-group pairings, then total score/record distance.
3. Pairing preference within equal score groups, using seeded upper/lower-half
   ordering, then a stable seed/entrant key for equal-cost algorithm inputs.

Choose integer scale factors from the number of pairs and maximum lower-priority
cost so lower criteria cannot outweigh higher ones. The matching must cover
every eligible entrant. Never publish a partial solver result as a valid round.
Saved fixtures are authoritative across dependency upgrades; deterministic
small fixtures and tests with different hash seeds guard generation behavior.

Past opponents are excluded from ordinary pairing edges, including matches
decided by forfeit. No entrant plays twice, pairs with themselves, or returns
after qualification/elimination/withdrawal. A repeat bye is allowed only when
no complete legal matching can use an entrant with fewer prior byes; the preview
labels it. Byes award the ordinary win credit without inventing played games.

If no complete no-rematch pairing exists, explain the conflict and offer a
separate **Allow required rematches** action. It requires explicit confirmation
and an internal reason, then minimizes rematches ahead of the normal pairing
costs. Publish the rematch exception as a safe Changes event without actor/note.
Never silently relax the rule. Manual adjustments obey the same coverage and
eligibility and bye constraints; rematches still require the explicit override.

## 9. Tie resolution and stage handoff

TieResolution records the tied set, positions available, originating standings
fingerprint, and method. It cannot include an untied entrant or award more places
than available. The TO previews and confirms either:

- **Extra matches:** two entrants play one decisive best-of series. Three or more
  play a separate single round robin mini-table among the tied entrants, using
  a single chosen best-of length. Rank by match wins, then head-to-head wins,
  then game difference. These games do not alter the original stage's points.
- **Manual decision:** explicitly select/order the tied entrants, with a required
  internal reason. Public Changes says the tie was resolved by organizer decision
  and shows the resulting selection/order, without exposing the actor or note.

If the extra contests leave another relevant tie, create another resolution for
that tied subset or choose a manual decision. Never loop automatically or invent
a qualifier. Extra matches use normal scheduling, score validation, corrections,
and public match/history views. They count toward a separate bounded generation
check using the same match budget.

Once the source's required outcomes are resolved, preview a handoff containing
the exact entrant IDs, proposed seeds/groups, source fingerprint, and destination
requirements. TOs may reorder the seeds before confirmation, retaining the
confirmed qualifier set. Save whether seeds follow source ranking or an explicit
TO order. Reordering is explicit and audited. Confirmation
creates the destination draft from those entrants; a separate preview/publish
step makes its fixtures public.

Changes to source results invalidate a tie decision when its tied set, cutoff,
or ranking inputs change. Do not silently preserve an old manual choice against
a new tied set. Recompute the source under the correction lock. A handoff may
remain valid only if the source is still complete with no required unresolved
ties, and its selected identities, eligibility, and destination seeds remain
valid. Recompute rank-derived seeds; retain an explicit TO seed order if its
qualifier set remains valid. Record revalidation against the new source
fingerprint without resetting that destination draw. Otherwise the handoff
appears in correction impact and requires confirmation again. A source that
needs replay cannot revalidate a handoff using its superseded results.

### Exceptional chain completion

A valid run can leave one or zero eligible qualifiers, or a previously published
destination's locked rules may no longer fit a corrected field. Never promote an
eliminated entrant merely to fill a place. The TO may configure a valid unpublished
destination where possible, or explicitly **End competition here** with an
internal reason and public outcome. One sole eligible qualifier can be awarded
the competition; zero, or multiple entrants without a valid decided winner,
ends it **Without a champion**. This does not rewrite the source's recorded ranks.

Preview and retire the remaining stage suffix in the same audited command. A
wholly unpublished suffix stays private. If any suffix stage was already
published/played, use the full correction impact/confirmation and reset permission
boundary, keep retired stage identities and old matches visible as historical
records, and preserve their public Changes. Nothing is hard-deleted. Confirming
ordinary handoffs and ending a chain are distinct actions.

## 10. Commands, locking, and correction effects

All writes enter named competition commands: configure/select entrants, save
draw, publish, schedule, set series override, start, save progress, finalize,
withdraw/disqualify, generate/publish Swiss round, resolve tie, confirm handoff,
and preview/apply correction. Unfold forms never update operational fields
directly. Commands accept an actor and expected Competition revision.

Use `transaction.atomic()` and the existing lock order:

1. Lock the owning `TournamentGame` row, matching registration services.
2. Lock its `Competition` row; enforce the one-to-one uniqueness in the database.
3. Lock affected registration/competition rows in a stable primary-key order as
   needed. Never acquire a different division lock from inside this command.
4. Validate permissions, revision, object scope, state, and command input; apply
   the entire state change, append ChangeSet, and increment revision once.

The division lock also prevents entrant approval changes racing publication.
This intentionally serializes commands within a division, including registration
operations: document that throughput ceiling with a `ponytail:` comment. Adopt
finer locks only if measurements justify the extra ordering complexity.

Wrong/stale revisions reject before mutation and return the refreshed-state
instruction. Duplicate form submissions cannot finalize or advance twice.
Validation, history, and revision commit together; failures leave no success
history. A lost response is recovered by reloading current state and Changes.
No background queue is required for core commands.

### Correction preview and application

A preview is read-only and includes source result before/after, every affected
match ID, live/final scores to clear, rounds/draws to supersede, tie resolutions,
and stage handoffs. The confirmation carries the original revision, a signed
digest of the canonical proposal/impact, and explicit reset consent. Recompute
impact under locks and reject if it differs. Never accept client-supplied lists
of records to reset as authority.

Apply these dependency rules:

| Change | Required propagation |
| --- | --- |
| Elimination score change with the same outcome/entrant routing | Keep dependent participants/results if their competitive inputs are unchanged; still update result history. |
| Elimination winner/loser or eligibility change | Re-resolve winner/loser slots transitively. Clear started/final dependent contests whose participants change, then re-evaluate further descendants and grand-final reset activation. |
| Round robin result change | Keep independent ordinary fixtures/results. Recalculate standings and affected tie resolutions, then revalidate or invalidate handoffs using Section 9. |
| Swiss confirmed pairing/standing input change | Supersede all later generated rounds, since pairings are global. Retain old rounds/results in history; regenerate and republish rounds from the corrected closed-round state. |
| Invalidated qualification or destination seeding | Supersede the entire affected destination draw and dependent later handoffs/draws. Keep the stage identity public with an awaiting-confirmation state. Reconfirm entrants and preview/publish replacement fixtures. |

For Swiss, confirmed W/D/L, bye, forfeit, opponent, and any score used by a
configured standings/pairing tiebreak are inputs. A score-only edit that changes
none of those inputs may preserve later rounds after fingerprint comparison.
Scheduling metadata is not a pairing input.

The entire reset/recalculation and its history are one commit. There is no public
window with corrected source scores and stale advancement. Already played
dependent matches can be reset only when included in the confirmed impact.
Within a retained draw, unaffected matches retain their IDs and results. When
a destination draw is replaced, every match in that draw is retired, including
any otherwise unchanged pairing; preview every live/final result being reset.
This conservative draw replacement is an explicit implementation boundary.
Replacement matches have new IDs. Superseded matches leave the active bracket,
but their prior outcomes remain in Changes and historical match detail.

## 11. Authorization, history, and public reads

Keep the existing flat Organizers group policy: active authenticated staff in
that group plus the relevant Django permissions; superusers retain their normal
access. Button visibility is not authorization. Check services, custom admin
URLs, forms, and object scope independently.

Use native permissions without adding new account roles:

| Operation | Required model permissions, in addition to organizer policy |
| --- | --- |
| View organizer workspace/history | Relevant `view_*` permissions, including `view_changeset` for private audit data. |
| Create competition | `add_competition`, with division visibility. |
| Configure/publish/generate/decide ties/confirm handoff/end a chain with wholly unpublished suffix | `change_competition`. |
| Schedule/start/score/edit match length | `change_match`; scope and state guards still apply. |
| Correct/reset results, including draws or handoffs | Both `change_match` and `change_competition`. |

Withdrawal/disqualification requires `change_competition` and also
`change_match` when its effects finalize or reset any published fixture.
Ending a chain with published/played descendants requires both permissions.

Grant intended permissions through the existing bootstrap command after
migrations. Do not grant ordinary organizers deletion or direct editing of
generated records/history. Custom admin forms call commands even for superusers.
Private ChangeSet is readable but not editable through the admin.
An organizer without `view_changeset` receives no private Changes link or audit
payload; direct audit URLs remain forbidden. Other actions retain the permissions
listed above and do not require access to earlier internal notes. The public
Changes view remains independently available through its public allowlist.

Construct public change items from an explicit allowlist of change kind,
timestamp, stage/round/match identifiers, public entrant labels, before/after
scores/outcomes, and safe qualification selections. Actor, actor/account IDs,
internal notes, private registration fields, and draft changes are absent from
the public response itself. Do not expose a generic model/history serializer.
History snapshots retain the public labels used at the time of the change.
Gate each public change item by its referenced data's visibility at that revision.
A correction can immediately report a reset of formerly published results, but
must not reveal a replacement draw's private fixtures, entrants, or decisions.
Their later publication emits its own public event. Draft events are never
retroactively exposed just because a later version was published.

Proposed read endpoints:

- `GET /api/tournament-games/{division_id}/competition/`: published stage list,
  competition revision, and public overview.
- `GET /api/competition-stages/{stage_id}/`: current public rules, entries,
  standings, and round summaries.
- `GET /api/competition-rounds/{round_id}/`: the current published round's matches;
  superseded rounds return 404 here and remain accessible through historical
  match detail and Changes.
- `GET /api/competition-matches/{match_id}/`: published current/historical match
  detail; a superseded match is clearly labelled and links to Changes.
- `GET /api/tournament-games/{division_id}/competition/changes/`: cursor-paginated
  public change sets, filterable by public stage/match; default 50, maximum 100.

Unpublished parent tournaments/stages/rounds/matches return 404, including direct
ID lookups and history filters. Superseded *previously published* match outcomes
may be read as historical records; superseded drafts remain private. Public
endpoints have the same allowlist even when the requester is a logged-in TO.
No authenticated mutation API is added for the SvelteKit client in this phase.

Build multi-query snapshots in a PostgreSQL read-only repeatable-read transaction
so a concurrent correction cannot produce mixed revisions. Set that isolation
before the first query inside the transaction and cover it with a PostgreSQL
test. Every response includes `competition_revision`, including round, match,
and paginated Changes responses. It identifies a consistent read, not a count of
public changes. When combining responses, the page verifies matching revisions
and refetches on a mismatch. After two unsuccessful retries, retain the last
coherent view or show a refresh state; never mix old advancement with new scores.
History pages retain their immutable entries even when a newer revision exists.
Use explicit refresh and navigation refetch; polling/push is Section 6.

## 12. Organizer and public presentation

### Django Unfold

The Competition workspace opens from a division link. Its primary sections are
stages, entrants, and Changes. A stage workspace shows setup/entries, fixtures,
standings where applicable, qualification, and Changes. A match page shows stable
ID, source slots, effective series length, schedule, status/scores, action forms,
and history. Search by match code and filter by stage, round, group, and status.

Use Unfold form/layout components, Django validation messages, and existing
GET-confirmation/CSRF-POST patterns. Simple custom templates can render a bracket
preview; do not build a new admin component framework or embed a second Svelte
application in Django. Result actions use explicit progress/final/correction
forms. A correction confirmation lists losses of live/final data prominently
and requires an internal reason. The public result history remains separate
from the full organizer audit view.

### SvelteKit

Add the competition route beneath
`/tournaments/[slug]/games/[gameId]/bracket`, with stage/round selection and a
Changes view. Keep links/navigation consistent with existing localized routes.
Use existing time-zone formatting and EN/VI message keys. User-supplied team and
player labels render as escaped text.

Elimination displays round columns, match cards, and native CSS/SVG connectors;
double elimination separates upper, lower, and finals. Mobile offers horizontal
scroll plus a round/list view with clear focus order. Round robin and Swiss
display semantic standings tables, round match lists, bye/rest/forfeit labels,
and qualification state. All surfaces show the server's effective series length.

Changes shows chronological public before/after outcomes, including resets and
manual qualification decisions. Historical match links are clearly labelled.
Unpublished data never appears in page props, HTML, fixtures, or hidden controls.
Empty/waiting/ready/live/complete/error states have useful next navigation or
refresh actions. Keep large views bounded by stage/group/round selection and
history pagination; do not render every match of a large round robin at once.

## 13. Delivery boundaries and proof

Deliver complete usable slices: common foundation + single elimination first,
then double elimination, groups, both Swiss presets, and stage/tie workflows.
Shared contracts are established before dependent agents implement against them.
This is one competition subsystem with format-specific work packages; completing
one format is not completion of the whole core.

The integration owner controls models/migrations, command contracts, permission
bootstrap, shared types/fixtures, URL/admin wiring, and reconciliation of tests.
Parallel agents own bounded format modules, admin workflows/templates, or public
components and their focused tests. They request shared-contract changes instead
of independently editing those files. The implementation plan assigns exact
files and prerequisites; this spec does not authorize product implementation.

Required evidence:

1. Pure algorithm tests cover seed order, uneven fields, route/loss invariants,
   round robin pair counts, legal complete Swiss matchings, deterministic
   fixtures, and standings/tie examples. Small Swiss graphs compare solver
   output to exhaustive legal matchings as a test oracle, not production code.
   Include upper-bracket double forfeits, empty finals/No champion, and a completed
   threshold stage whose suffix cannot accept its remaining qualifier set.
2. PostgreSQL tests cover simultaneous TO commands, publication/approval races,
   stale previews, duplicate POSTs, rollback/history atomicity, coherent reads,
   and corrections across played matches, Swiss rounds, and multiple stages.
3. Permission/privacy tests cover nonstaff, unrelated staff, partial/view-only
   organizers, inactive accounts, superusers, direct URLs, and public Changes
   payloads/SSR data. GET requests cannot mutate competition state.
4. Real Django + Svelte browser journeys cover setup → preview → publish → score
   → correction → Changes → qualification/handoff → completion, including both
   Swiss presets, both final policies, and both tie-resolution methods.
5. Responsive/keyboard/EN/VI checks, relevant registration regressions, migration
   checks, backend lint, frontend type/build checks, and realistic isolated seed
   fixtures precede declaring a slice complete. Benchmark bounds before exposing
   the configured maximum field; no results are claimed in this design document.

Migrations are additive and do not rewrite registrations. Deploy migrations,
then update organizer permissions, then expose the new navigation. Keep all new
records/history when rolling back application access; do not reverse/drop the
competition schema after real events have been recorded. An operator runbook
must cover stale edits, forfeits, tie resolution, corrective resets, history,
and restoring access without losing tournament data.

The core exit gate is all supported formats, public/private Changes separation,
and safe ordered-stage operations through Unfold. Live push updates and Full Beta
hardening retain their separate project gates.
