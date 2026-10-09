# Ordered multi-stage competitions

Date: 2026-10-09. Branch: `feat/tournament-brackets`.

Status: **Conversational design approved; written specification awaiting review.**
This document defines proposed behavior, not completed implementation.

This is the next supported-format slice of the
[competition core design](2026-09-23-competition-core-design.md). For this slice,
the decisions below replace that document's rank-derived/manual handoff seeding
and editable draft stage suffix. Other match, authorization, privacy, and history
contracts continue to apply.

## 1. Outcome and confirmed decisions

One Competition can contain an ordered chain of Round Robin, single-elimination,
and double-elimination stages in any combination, including repeated formats.
The organizer specifies advancement counts; the system calculates qualifiers.
Only the first stage selects approved registrations. Each subsequent stage uses
exactly the preceding stage's qualified entrants.

The user approved:

- Stage order and every advancement count are set and locked before publishing
  the first stage.
- Round Robin uses a qualifying-place count for each group; elimination uses
  Top-N finishing places.
- All required source matches must finish, including groups where every team
  advances. A double-elimination reset final marked not required is not played.
- A tie crossing a qualifying cutoff requires an organizer choice between
  Extra Matches and Manual Decision.
- Next-stage draws wait for source completion and resolved qualification.
- Qualified teams enter a saved, unrestricted random draw. Source ranking does
  not determine destination slots or byes; same-group rematches are permitted.
- Draw generation, preview, and publication are separate from entering the last
  source result. Refresh never creates or reshuffles fixtures.
- Corrections preserve an existing later draw when its source remains complete
  and the qualified entrant set remains valid and unchanged. Otherwise affected
  downstream draws require explicit retirement and replacement, with history
  preserved.

The uneven-group examples are witnesses to general rules, not special cases.
Three groups of sizes 3–3–2 with two places each advance six of eight entrants.
Sizes 3–2–2 with the same counts advance six of seven. Other valid partitions and
per-group quotas must work under the same invariants.

## 2. General rules and validation

### Stage fields and group partitions

Retain the current supported bounds: 2–256 real entrants per draw, at most 16,384
ordinary generated matches per draw, and the existing extra-match budget.
Registration capacity remains separate.

For a Round Robin stage with incoming field size `n`, planned group sizes
`s[1..g]`, and qualifying-place counts `q[1..g]`:

```text
sum(s) = n
each s[i] >= 2
each 1 <= q[i] <= s[i]
outgoing field size = sum(q)
ordinary match count = meetings * sum(s[i] * (s[i] - 1) / 2)
```

Group sizes need not be equal or differ by only one. Counts need not be equal.
Every real entrant belongs to exactly one group in the current draw; group names
are unique within the stage. An odd group size creates rests under the existing
circle schedule, not extra entrants or points.

Balanced group sizes are a setup convenience. The organizer may configure any
partition satisfying these equations and the existing bounds. Later-stage group
membership comes from the saved random entrant order, partitioned by the planned
sizes in group order. No ranking comparison between unequal groups is needed.

For a nonfinal elimination stage, set an integer quota `k` with `1 <= k <= n`.
The expected incoming size of its successor is `k`. Advancing everyone is valid,
but the entire source schedule still finishes. A final stage has no outgoing
handoff; retain its existing format-specific result/champion semantics.

### Validate the whole chain before publication

Start with the first stage's approved selected field, then calculate each
successor's expected incoming count using the preceding quotas. Before first
publication, reject any stage whose format, group partition, quotas, or generated
match budget cannot accept that count. A successor requires at least two real
eligible entrants. A quota of one can describe a final result but cannot feed a
two-entrant destination.

First publication freezes stage order, formats, group sizes, outgoing quotas,
and qualification criteria. Stages cannot be appended, removed, reordered, or
have those rules changed afterward. Existing allowed scheduling and round/match
series-length changes before play remain available. No later fixtures are
generated as part of freezing this plan.

Actual eligibility is checked again at handoff and destination publication. If
the qualified field no longer fits the locked plan, explain the blocking rule.
Do not trim qualifiers, change quotas, add registrations, or substitute a lower
finisher to make the field fit. Eligibility changes do not silently erase old
matches. Withdrawal/disqualification operations and a new exceptional chain-end
command are outside this slice; existing result corrections remain available.

## 3. Qualification and placement

### Round Robin

Reuse configured points, ordered tiebreaks, final-results-only standings, and the
existing group cutoff-resolution calculation. Take exactly each group's quota.
Qualification remains provisional until all ordinary fixtures finish. A group
where `q = s` still plays all its fixtures, although its qualifier membership is
already determined. Ties wholly within or outside the qualifying set need no
resolution because destination ordering is random.

### Single elimination

Complete the ordinary bracket. The champion is first; entrants exiting in the
same ordinary round share a finishing band, with later exits ahead of earlier
exits. Take complete bands until the quota is reached. If the quota cuts a band,
resolve only that tied band for the remaining places.

Thus an eight-team Top-3 cutoff takes the champion, runner-up, and one resolved
semifinal loser. Top-4 takes both semifinal losers without an unnecessary
third-place contest. Byes and empty slots never create additional finishers.

### Double elimination

Use the actual deciding grand final, including the reset final when activated,
to identify the champion and runner-up. Other entrants are ranked by their
terminal exit from the lower bracket: later lower-round exits outrank earlier
ones, and exits in the same lower round are tied. An upper-bracket loss that
routes an entrant to the lower bracket is not a terminal finishing position.

Preserve the existing no-reset policy, including its decisive final, and the
two-entrant case with no separate lower contest. Structural byes and conditional
finals do not create fictitious losses. A lower-bracket double forfeit places both
real entrants in that lower round's exit band. A double forfeit in the deciding
grand final leaves its real finalists tied in the highest band and records no
champion. An upper-bracket double forfeit produces no lower-bracket route or
standard lower-round placement; if that missing placement prevents determining
the configured Top-N set, qualification is blocked with an explicit explanation.
Do not assign a fictitious lower contest or invent a placement using win totals.
An exceptional outcome with no champion must remain labelled that way even if
eligible entrants qualify for a later stage through a resolved finishing band.

For both elimination formats, a single forfeit is a recorded loss for placement.
Placement does not impose a new competition-wide disqualification: entrant
eligibility still comes from the existing registration and entrant state. An
inconsistent or incomplete terminal placement blocks qualification rather than
falling back to entrant ID, display order, number of wins, or score difference.

### Extra Matches and Manual Decision

Generalize the existing TieResolution workflow to a group cutoff or an
elimination draw's placement cutoff. A resolution references exactly the tied
source entries and available places; it cannot include an untied entrant.

- Manual Decision orders the tied contenders and selects the required prefix,
  with an internal reason. The order resolves this cutoff only; it does not seed
  the next stage.
- Extra Matches use a decisive best-of match for two contenders, or the existing
  single-round-robin mini-table for larger tied sets. Rank that mini-table by
  match wins, head-to-head wins, then game difference, independently of ordinary
  stage standings.
- A remaining cutoff tie requires another explicit choice. Never loop, resolve
  ties randomly, or generate extra contests automatically.

Tiebreak contests use normal scheduling, scoring, series-length locking,
corrections, and history. They do not change ordinary placements outside the
tied band, feed normal elimination winner/loser routes, or change group points.
The source remains awaiting resolution until every required cutoff is decided.

## 4. Delayed, saved random draws

An organizer can configure all stages before play, but cannot generate a
successor's draw while the preceding source is unfinished or awaiting a required
tie resolution. Configuration and fixture generation are distinct operations.

The Generate Next Stage Draw POST command:

1. Locks the division/competition and validates the submitted revision.
2. Resolves the immediately preceding stage's current published draw and
   recalculates its completion, qualifier set, and qualification fingerprint.
3. Requires the exact configured number of unique eligible qualifiers, all from
   the same Competition and division, and validates destination capacity.
4. Uses the existing system random source to shuffle that set once. Records the
   permutation and source-entry links in a new destination draw.
5. Generates the destination's fixtures through its existing format generator,
   records the source fingerprint and command history, and returns the private
   saved preview.

Publication is a separate POST which rechecks source validity, registration
eligibility, saved entrants, fixtures, and revision. It never generates a new
permutation. Repeated submission of a used revision cannot create a second draw.
Generating again while a current draft exists reuses that draft; an explicit
regeneration operation must be recorded and supersede its earlier draft version.
Published draws cannot be directly regenerated.

Retain the existing `StageEntry.seed` as an internal draw-position identifier
needed by the bracket generator and existing API consumers. For later stages it
is the saved random position, not a strength ranking. Product controls describe
draw positions and random draws; they do not offer manual ordering or a seeding
toggle for incoming qualifiers.

For uneven elimination fields, shuffle the full qualifier set before using the
existing padded bracket generator. Its bye-bearing positions consequently go
to random qualifiers. For six entrants, the eight-slot bracket has exactly two
first-round byes. For later Round Robin, distribute the shuffled order into the
locked group sizes. Each qualifier appears exactly once.

## 5. Ownership and persisted state

Extend `server/competitions`; catalogue, registration, payment, and roster
ownership stay in their existing applications. Keep qualification calculations
in format code and shared handoff/publication/correction invariants in guarded
competition commands. No workflow engine, provider interface, or dependency is
needed.

| Record | Change and responsibility |
| --- | --- |
| Competition | First stage's immutable publication timestamp supplies the whole-plan lock; reuse the revision and command boundary. |
| Stage | Store the elimination outgoing quota when a successor exists; retain order, format, setup, completion, and identity. |
| StageGroupPlan | Stage-owned ordered group definitions with name, planned size, and qualifying-place count, available before any destination draw exists. |
| StageGroup | Keep draw-owned group snapshots and memberships so superseded draws retain their original groups and rules. |
| StageDraw | Add a protected preceding source-draw link and qualifying-input fingerprint for later draws. Creation/history records the confirmed handoff; no independent handoff workflow record is required. |
| StageEntry | Reuse `source_entry` to link each advanced entrant to the preceding draw, and `seed` to retain its saved random position. |
| TieResolution | Add draw ownership and make group scope optional, supporting elimination placement bands as well as existing group cutoffs. Backfill draw ownership from existing groups. |
| Round, Match, MatchSlot, ChangeSet | Reuse tiebreak sections, normal match operations, stable identifiers, and attributable private/public history. |

Stage-owned group plans are needed to validate and freeze arbitrary future group
partitions before source completion. They are setup rules, not empty placeholder
draws. Keeping draw-owned snapshots prevents replacement draws from rewriting
historical group memberships or qualification rules.

Command validation enforces immediate predecessor order, same-competition source
links, source/destination entrant identity equality, matching tie scopes, and
valid group partitions. Retain database uniqueness/positive-value constraints
and protected historical references. A draw's source fingerprint covers the
locked qualification rules, relevant final results, tie decisions, and qualified
identities. Actors, notes, schedules, and display ordering are not qualification
inputs. A whole-competition revision is checked separately for stale commands.

## 6. Corrections across stages

Extend the existing signed impact-preview and atomic correction command. First
project the source-format effects: dependent elimination matches, group standings,
and relevant tie resolutions. Then assess every affected successor in order.

A destination draw remains valid only when its source is still complete, every
required qualification tie remains resolved, and the same eligible entrant set
still qualifies. A changed finishing order alone does not invalidate a random
draw. Record revalidation and update its qualifying-input fingerprint while
preserving its permutation, groups, match IDs, schedules, and results.

If the source needs replay, a tie decision becomes invalid, eligibility fails,
or qualified identities change, supersede the entire destination's current draw
and dependent later draws. This applies to both private drafts and published
draws. The correction preview lists each affected draw and every live/final
result that will leave the active competition. A signed confirmation must be
recomputed under locks and rejected if its impact or revision changed.

Require the existing competition/match correction permissions and explicit
consent for affected downstream play. Preserve superseded draw, entry, group,
round, match, result, and resolution records. Keep previously published stage
identities public in an awaiting-replacement state; private draws remain private.
Superseded matches are historical and cannot be operated through direct URLs.
Replacement requires source completion, a new recorded random draw, preview,
and publication under the existing stage's locked rules.

Apply the source change, suffix retirement/revalidation, and ChangeSets in one
transaction. Public reads must never combine corrected source scores with stale
current advancement. Reuse consistent snapshots and revision-mismatch handling.

## 7. Organizer and public presentation

Keep the current Unfold Competition workspace and add stage selection. Before
first publication, setup shows the full stage order, formats, group sizes,
advancement counts, expected incoming counts, and validation failures. The
publication preview makes the whole-plan lock explicit.

Each stage exposes its setup, current fixtures, applicable standings/placement
bands, qualifying set, cutoff ties, and Changes. Future stages display Waiting
for previous stage until a valid field exists. The completion view offers
Generate Next Stage Draw when allowed; it does not let the organizer replace
qualifiers or alter their order. Preserve stage selection in action forms,
return links, group/round filters, and match navigation.

The public SvelteKit competition page selects among public stages and shows
published qualification rules, outcomes, and advancement. Saved future-stage
setup, private entrants, draft fixtures, actors, reasons, and fingerprints never
appear in public API responses, page props, or HTML. A replacement-waiting public
stage explains the state and links to preserved Changes. A previously published
superseded match remains clearly historical.

Extend explicit response allowlists and existing EN/VI localization. Preserve
public competition/stage/round/match endpoints and numeric entry-position fields
for compatibility. Existing first-stage draw choices remain available; this
slice removes rank/manual seeding only from later-stage handoffs. No public
mutation endpoint or new frontend admin application is added.

## 8. Compatibility, migration, and scope

Migrations are additive except for the supported nullable group scope on ties.
Backfill group plans for current Round Robin setup and draw ownership for
existing TieResolution rows without regenerating draws or fixtures. Retain
published match IDs, results, display snapshots, histories, and existing quotas.
Previously published single-stage competitions remain locked single-stage plans;
this slice does not permit attaching a stage after that publication.

Legacy command callers that omit stage identity continue to address stage 1;
updated multi-stage admin flows explicitly address the selected stage. Centralize
stage lookup and validation rather than duplicating sequence assumptions across
format commands. Existing seed fixtures must remain rerunnable and preserve
published records. Add synthetic multi-stage examples through guarded commands.

Non-goals: Swiss, branching/merging stage graphs, entrants from other divisions,
rank-based handoff seeding, group-rematch restrictions, automatic progression on
last-score submission, automatic scheduling, realtime, withdrawal/disqualification
commands, exceptional chain-ending commands, changes to registration/payment,
or rules for modifying an already locked stage plan.

## 9. Acceptance and focused proof

The proof must exercise rules across variations, not only reproduce the original
uneven-group example. Use table-driven cases and bounded enumeration of small
valid partitions/quota combinations; no new property-testing dependency is
required. Assert exact eligible membership, quota totals, unique draw positions,
saved permutations, and complete required source play.

| Case | Required behavior |
| --- | --- |
| 3–3–2 groups, two places each | Six of eight qualify; both members of the two-team group play; next single-elimination draw has two random byes. |
| 3–2–2 groups, two places each | Six of seven qualify under the same rules, with no special-case branch. |
| Arbitrary unequal groups and unequal quotas | Group-size sum equals the field; qualifiers total the quotas; each saved random assignment respects planned sizes. |
| Everyone advances, including tied places | Full source play is required; no tie resolution solely to order already-qualified teams. |
| Invalid partitions/quotas/budgets | Reject before first publication and leave no partial lock, draw, or history. |
| Invalid later-stage capacity | Reject the entire plan before stage 1 publication, including a one-qualifier destination or undersized groups. |
| Any supported source/destination combination | Exercise all nine format transitions and at least one chain of three or more stages. |
| Single-elimination Top-3 and other split bands | Correct complete bands; required Extra Matches or Manual Decision at the cutoff. |
| Double-elimination finishing bands | Correct terminal lower-round placement under reset/no-reset, two-team and uneven fields, byes, and forfeits. |
| Remaining tie after extra play | Await another explicit resolution; no automatic winner or next-stage draw. |
| Random draw preview, refresh, repeated POST | Exactly the qualified set; saved order persists; stale/duplicate commands create no additional draw. |
| Source correction with unchanged valid qualifiers | Keep the existing random permutation and all unaffected destination results. |
| Source correction changing qualifiers or requiring replay | Preview and atomically supersede the affected suffix, preserve historical results, and require replacement publication. |
| Tie-result correction and nested decisions | Revalidate source qualification and invalidate affected suffixes under the same rules. |
| Registration eligibility changes during handoff/publication | Reject stale eligibility under shared locks without silently substituting entrants. |
| Unauthorized or cross-stage/direct-URL operations | Enforce permissions, current-draw identity, CSRF, scope, and revision checks. |
| Public privacy and coherent snapshots | No draft/actor/private-data leakage; no mixed-revision advancement; historical published records remain readable. |
| Migration from existing saved competitions | Preserve published IDs, fixtures, scores, quotas, and histories; maintain one current draw per stage. |

Run focused PostgreSQL command/concurrency, model/migration, API/privacy, and
organizer tests; relevant frontend type/build and stage-selection tests; and one
real organizer/public browser journey from setup through handoff and a correction
after downstream play. Include responsive, keyboard, and EN/VI stage navigation.
Existing single-stage single/double elimination and Round Robin regressions must
pass. If an environment prevents PostgreSQL or browser proof, report that limit
without substituting a broader completion claim.

## 10. Written review handoff

Review this specification before writing the implementation plan. No product
code, migrations, or new runtime tests have been changed. The plan will break
the reviewed design into the responsible model, command, format, organizer,
public, fixture, and verification changes.
