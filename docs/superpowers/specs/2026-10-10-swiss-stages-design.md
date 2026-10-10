# Swiss qualification stages

Date: 2026-10-10. Branch: `feat/tournament-brackets`.

Status: **Design draft for written review; no implementation authorized.**
The decisions below consolidate the current planning conversation. Technical
details describe proposed behavior, not features already delivered.

This refines the Swiss portion of the
[competition core design](2026-09-23-competition-core-design.md) and extends the
delivered [multi-stage design](2026-10-09-multi-stage-competition-design.md).
It replaces the older Swiss upper/lower-half pairing preference and proposed
ranking-based handoff order. Existing non-Swiss stage plans retain their rules.
Delivery remains tracked in [BRACKET-TODO](../../BRACKET-TODO.md).

## 1. Purpose and placement

Swiss reduces its incoming field to qualifiers for later competition stages.
Both fixed-round and win/loss-threshold Swiss are supported as the first or
an intermediate stage of a competition containing at least two stages.

- A Swiss stage cannot be standalone or final. Every Swiss stage must have a
  successor; it never declares the competition's champion.
- Consecutive Swiss stages are supported, including different Swiss presets
  in the same chain. A Swiss stage may follow or precede any supported format
  when their locked advancement rules and actual fields are compatible.
- The complete stage chain must be configured before the first fixtures become
  public. An incomplete private setup may be saved, but cannot be published.
- The final stage must use a supported non-Swiss format.
- Format availability, stage reordering, direct command calls, and publication
  validation must all enforce this placement rule.

Examples include Swiss → playoffs, Swiss → Swiss → playoffs, three Swiss
stages → playoffs, and double-elimination play-ins → Swiss → playoffs.
These describe supported format ordering, not a promise to reproduce every
CS Major or Worlds entrant-admission and seeding rule. The existing chain
still takes a later stage's entrants exclusively from the immediately preceding
stage's eligible qualifiers; direct invitations into later stages are separate
from this scope.

Organizer operations stay in Django Unfold; public views remain read-only.
Reuse the existing competition, entrants, stages, draws, rounds, matches,
results, qualification, Changes, and correction boundaries.

## 2. Setup, suggested rounds, and limits

`N` is the actual incoming field of this Swiss stage: selected entrants for
stage 1, or confirmed eligible qualifiers from its predecessor for a later
stage. One team or one solo player is one entrant. Retain the existing support
limits of 2–256 entrants, 64 Swiss rounds, and the competition core's match budget.

For fixed-round Swiss with a known incoming count, prefill `ceil(log2(N))`.
The organizer may change it before the competition's first publication. Label
it **Recommended rounds**, not a guarantee of distinct final positions.
Updating the field before publication updates the recommendation and revalidates
the saved choice; it must not silently overwrite a saved custom value.

Proposed handling for review when a later Swiss stage's incoming count is
outcome-dependent: lock either the automatic `ceil(log2(actual N))` rule or an
explicit custom count before the competition's first publication. Show the
formula with its count pending until the field is known. Resolving the locked
formula at handoff gives the organizer no new round-count choice. Save the
resolved count with that draw; it cannot drift while that draw is in use.

Use this agreed configuration bound:

```text
field_round_limit = N - 1, when N is even
field_round_limit = N,     when N is odd and byes are used
round_limit = min(64, field_round_limit)
```

Fixed rounds must be an integer from 1 through `round_limit`. Threshold targets
`W` and `L` must be positive integers with `W + L - 1 <= round_limit`.
For threshold Swiss this is a conservative setup policy, not a mathematical
guarantee that all future pairings will be possible. No additional
"recommended rounds + 2" duration cap is introduced.

The field bounds reflect unique-matchup capacity for ordinary fixed rounds.
Neither these bounds nor the logarithmic recommendation prove that a particular
result history admits a complete next round. Pairing validation is still
required at every generation. A rematch override does not bypass setup limits.

Revalidate a later Swiss stage's round count or W/L targets, Top-N quota where
applicable, and match budget against its actual incoming field before generating
or publishing its draw. An incompatible custom count, threshold, or quota blocks
the handoff; never shorten it or change the target after seeing qualifiers.

Before publishing the competition's first fixtures, lock stage order, formats,
the first-stage field and starting seeds, each stage's round-count policy or
W/L targets, points and tiebreaks, qualification policies, group counts, group
advancement quotas, and allocation rules. Later fields follow those qualification
policies; their starting seeds are saved at the handoff and fixed before that
stage's publication. Existing valid scheduling and before-play series overrides
remain available through their established controls.

## 3. Results, standings, and qualification

### Fixed rounds

Everyone still eligible receives one match outcome or bye per ordinary round.
Allow decisive best-of and fixed-game series with draws, using the existing
result validation. Retain the agreed defaults: win/draw/loss points 3/1/0 and
tiebreaks opponent points, then game difference, then games won. Match wins
remains an available configured tiebreak.

Opponent points sums current confirmed match points of opponents actually
assigned in the stage. Each meeting contributes, including forfeits and
explicitly allowed rematches; a bye has no opponent. This is the existing
esports preset, not a claim to federation-specific adjusted Buchholz rules.

Configure Top-N advancement before publication, with an integer quota between
2 and the entrant count. Since another stage must follow, the quota must also
fit the destination's requirements. Finish all configured rounds before
resolving qualification.
Use existing explicit extra-match or recorded manual-decision workflows for
a tie crossing the cutoff. Do not use starting seeds to silently select a
qualifier. Tiebreak contests are separate from the ordinary Swiss round budget
and do not change the original stage's points.

### Win/loss thresholds

An entrant qualifies upon reaching W match wins and is eliminated upon reaching
L match losses. Only decisive best-of series are permitted. Individual game
wins do not count toward the threshold. Qualified and eliminated entrants do
not appear in subsequent ordinary Swiss rounds.

A bye counts as a normal match win, including a qualifying win, without
inventing played games or an opponent. A double forfeit gives both entrants
one loss. The stage requires at most `W + L - 1` completed rounds when every
active entrant receives one decisive outcome per round. An unresolved pairing
conflict blocks progress; the bound does not authorize an invented result.

All eligible threshold-qualified entrants advance. Do not impose a separate
Top-N trim, assume exactly half always qualify, or select a Swiss champion.
Complete the stage when no active entrants remain, then validate the actual
qualified field for the next stage.

## 4. Starting seeds and folding

Save the stage's initial manual seed order or random draw once. Later Swiss
stages use the existing saved random handoff to assign their own starting seeds.
These seeds remain the ordering within score groups throughout that stage;
standings tiebreaks do not reseed entrants between rounds.

Every new Swiss stage starts with fresh points, W/D/L, bye counts, and opponent
history. A qualifier from an earlier stage starts as an active entrant in the
new stage. Earlier results remain visible as history but do not count toward
the new stage's standings, exit targets, or rematch restrictions. Meeting an
opponent from another stage does not require the within-stage rematch override.

Fixed-round mode groups entrants by match points. Threshold mode groups them
by win/loss record. Within a group, prefer folding: best starting seed versus
worst, second-best versus second-worst, and so on. Eight entrants initially
pair 1–8, 2–7, 3–6, 4–5. In an odd first-round field, preserve the previously
agreed last-seed bye, then fold the remaining entrants.

This adopts the folding and cross-group opponent search described by
[FACEIT's Swiss guide](https://support.faceit.com/hc/en-us/articles/17983874189852-Tournament-formats-Swiss-system),
while retaining our own approved bye, points, and organizer-override rules.

## 5. Complete pairings and exceptional rematches

Compute a complete matching for the whole round. Do not commit greedy pairs
one by one: a locally valid pair may strand other entrants even when a different
complete round would avoid all rematches.

The ordinary solver excludes previous opponents from all earlier current
Swiss rounds in this draw, including forfeited matches. Superseded rounds do
not contribute current opponent history. Self-pairings, duplicate appearances,
and inactive, qualified, or eliminated entrants are invalid.

Preserve the existing bye-fairness priority: minimize prior bye count, then
prefer the entrant with the fewest points (fixed rounds) or fewest wins and
most losses (threshold mode), then the worst starting seed. A repeated bye is
allowed only when no complete legal matching can use an entrant with fewer
prior byes, and the preview must identify it.

Among complete legal solutions under that bye policy, minimize cross-group
pairings, then score/record distance, then deviations from folding. Try
alternative partners in the same group, adjacent groups, and progressively
farther groups as needed. These are whole-round preferences, not a sequence
of irreversible local choices. Use stable seed order to resolve equal pairing
preferences. Avoiding a repeat opponent outranks keeping a folding pair or
keeping entrants within their original group.

Retain the approved plan to use a maintained general graph matching solver
(NetworkX), with bounded integer priorities and deterministic fixtures. Lock
and verify the dependency during implementation; do not build a custom blossom
solver or exponential production search.

If no complete no-rematch round exists, explain the conflict and offer the
separate **Allow required rematches** action. Require explicit organizer
confirmation and an internal reason. With that exception authorized, minimize
the number of repeat pairings ahead of the ordinary preferences. Record the
exception in public Changes without exposing the actor or internal reason.
Never publish a partial pairing or silently relax opponent history.

Any manual pairing adjustment must satisfy the same coverage, eligibility,
bye, and rematch-authorization rules.

## 6. Round operation and corrections

Generate only one next round, after every current-round match has a final
outcome and unresolved result decisions have been handled. Save the source
fingerprint, exact pairings, bye, and any rematch authorization. A private
preview explains cross-group pairs and exceptional decisions. Publication is
an explicit action; refresh never reruns the solver or changes a saved draw.

Reuse organizer authorization, competition revision checks, transactional
locking, and Changes. Concurrent generation must not create two current
versions of the same round. Reject stale previews when their inputs change.
Unpublished future rounds remain private in both the UI and public API.

Apply the existing correction contract: a confirmed change to a Swiss pairing
or standings input supersedes all later generated rounds. Preserve their
fixtures and played results as history, with explicit reset consent when
downstream play is affected. Regenerate from the corrected completed rounds.
Scheduling changes alone do not invalidate pairings. Revalidate cutoff
resolutions, qualified membership, and every affected downstream draw in the
same correction transaction.

## 7. Locked plans with outcome-dependent incoming counts

Fixed-round Top-N supplies a known configured count. Threshold Swiss supplies
the actual eligible set reaching W, which can vary with byes and exceptional
outcomes. The plan must distinguish that unresolved count from a promised
fixed quota. Validate known counts and structural constraints before first
publication, and show that the threshold handoff still needs its actual field
validated. Do not promise a guaranteed qualifier count for arbitrary outcomes.

An elimination successor uses that actual field and the existing bye rules.
A Swiss successor consumes the actual qualified set, validates its own locked
settings against that field, and starts a fresh stage as specified above.
Another threshold Swiss stage produces another outcome-dependent outgoing
count; do not assume uncertainty ends after the first handoff.

For a round-robin successor whose incoming count is outcome-dependent, lock
the group count, group order, per-group qualifying places, and the following
allocation rule before any fixtures become public:

1. Reserve each group's minimum: at least two entrants and at least its locked
   qualifying-place count.
2. If the actual field cannot supply those minima, block the handoff.
3. Allocate remaining places to the currently smallest group, breaking ties
   by the locked group order. This makes sizes as even as the quotas permit.
4. Calculate sizes before assigning entrant identities. Assign the complete
   qualified set through the existing saved random handoff; the organizer
   cannot choose different sizes after seeing who qualified.

For two groups advancing two entrants each, fields of 7, 8, and 9 produce
4+3, 4+4, and 5+4 respectively. Unequal quotas may require unequal minima;
the published allocation rule still applies deterministically.

Round-robin quotas, elimination quotas, and fixed-round Swiss Top-N quotas
supply known configured outgoing counts. Validate the next stage against that
count; a later threshold Swiss stage can make its own successor's incoming
count outcome-dependent again. Apply this distinction through the entire chain.

Recompute automatic group sizes and any formula-based Swiss round count when
a source correction requires a replacement draw, using the same locked rules
and preserving the old draw's resolved settings and results in history. Never
reduce locked quotas, discard qualifiers, or add replacement entrants to make
a handoff fit. Invalid eligibility or too few qualifiers blocks advancement
with an explanation.

This extends the current exact-incoming-count assumptions in
`stage_commands.validate_stage_plan` and `handoff_commands._source_field`.
Keep the existing registration eligibility checks, exact qualified membership,
source lineage and fingerprints, saved random assignment, and separate
preview/publication. No new ranking-based handoff or seed-order tie decision
is introduced by Swiss starting seeds.

## 8. Delivery scope and proof

The implementation plan must cover persisted Swiss settings and round history,
pairing and standings calculations, commands and correction impact, stage-plan
and handoff validation, organizer controls, allowlisted public reads and views,
and rerunnable synthetic fixtures. Reuse shared UI and match operations rather
than creating a separate Swiss application.

Required focused evidence includes:

- Accept first and intermediate Swiss, consecutive Swiss presets, three Swiss
  stages followed by playoffs, and elimination → Swiss → playoffs. Reject
  standalone and final-stage Swiss, including direct requests and invalid
  stage reordering; reject publication without a successor.
- Verify suggested counts, integer validation, odd/even bounds, W/L bounds,
  field changes, and whole-plan publication locking. Cover a later-stage
  automatic count resolving from the actual field, incompatible locked custom
  settings blocking handoff, and recomputation only for a replacement draw.
- Verify folding and saved seed ordering, a greedy-pairing counterexample,
  adjacent and distant group moves, complete coverage, forfeit history,
  no-rematch dead ends, minimum-rematch overrides, and bye fairness.
- Check small matching cases against exhaustive reference solutions and test
  deterministic fixtures under different hash seeds.
- Exercise both termination modes, drawn fixed-game matches, qualifying byes,
  double forfeits, cutoff decisions, and exclusion after threshold exit.
- Verify stage-local starting seeds, points, records, bye counts, opponent
  history, and active status after advancement. Prior-stage opponents are legal
  in the new stage, while within-stage repeats still require authorization.
- Verify fixed and variable incoming fields, the 7/8/9 allocation examples,
  unequal quotas, insufficient fields, unchanged locked quotas, and repeated
  transitions between known and outcome-dependent counts in longer chains.
- Cover stale and concurrent round generation, correction of earlier rounds
  after later play, cutoff invalidation, downstream retirement, and private
  preview/history boundaries.
- Preserve existing non-Swiss data through migration and verify organizer and
  public workflows in English/Vietnamese and at narrow viewport widths.

No new withdrawal/disqualification commands or UI, exceptional competition-ending
workflow, provider integration, or realtime delivery is added to this slice.
Pairing and handoff commands must still reject ineligible entrants. If a stage
cannot continue under its published rules, retain the blocked state and history;
do not invent an automatic competition-ending decision.

After written design review, produce a separate implementation plan. This
document does not authorize implementation or mark any Swiss delivery task done.
