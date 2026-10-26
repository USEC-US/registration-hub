# Competition withdrawals, exceptional endings, and recovery

Date: 2026-10-26
Status: Approved, implemented and independently reviewed on 2026-10-26. See the [completed plan](../plans/2026-10-26-competition-lifecycle.md) and [operating/release guide](../../testing/competition-lifecycle.md) for evidence and remaining limits.
Builder review: 2026-10-26, no important unanswered questions.
Branch at discovery: `feat/tournament-brackets`, `95ed9eb`.

## Intent and scope

Finish the remaining bracket-core operations so organizers can handle entrants
leaving a competition, an impossible stage continuation, and mistakes in those
decisions without losing published history. Deliver commands, organizer actions,
public presentation, realistic fixtures, and release evidence together.

The foundation is the approved
[competition design](2026-09-23-competition-core-design.md), especially Sections
3, 5, 9, 10, and 11. Ordered-stage and Swiss designs still govern their formats.
This document fills the deferred lifecycle slice; it does not change scoring,
locked stage rules, registration/payment ownership, or public privacy rules.
Realtime, provider integrations, TFT, organizer translation, merging, and
production deployment are outside this implementation pass.

## Decisions and approaches

The user explicitly chose:

1. An exceptional ending can be reopened through a confirmed correction with an
   impact preview.
2. Reopening keeps retired later-stage fixtures historical. Replacement draws
   need fresh previews and explicit publication.
3. Restoring a withdrawn/disqualified entrant previews and undoes forfeits
   caused by that removal, with confirmation of affected later play.

Already approved rules: preserve results preceding removal; resolve remaining
published unplayed fixtures as forfeits; use double forfeits when both sides
are unavailable; explicitly confirm live-match forfeits; exclude inactive
entrants from future Swiss pairings and advancement; retain all audit history.

The implementation approach is to extend the existing competition commands,
format projections, signed previews, division locks, and ChangeSet history.
This fits the chosen correction workflow. A separate lifecycle engine would
duplicate those invariants; direct admin status edits would bypass them.
Neither is a suitable alternative. Exact module boundaries and provenance
storage are implementation decisions subject to the invariants below.

For reopening, the alternative was to resurrect old fixtures whose inputs still
match. The user chose replacement draws instead: this makes public history and
organizer confirmation explicit at the cost of generating a new draw.

## Current implementation and affected ownership

- `CompetitionEntrant` already stores ACTIVE/WITHDRAWN/DISQUALIFIED, but has no
  supported lifecycle command or organizer action.
- Elimination result routing and automatic resolution live in `commands.py`.
  Their current winner/loser propagation does not exclude inactive entrants.
- Qualification and handoff projections live in `qualification.py` and
  `handoff_commands.py`. Handoffs already enforce active, approved entrants and
  preserve or supersede downstream draws through correction impact.
- Swiss persists round versions, pairing fingerprints and historical rounds.
  `_validate_swiss_field` currently requires every original entrant to remain
  active/approved, and `_rank` does not incorporate removal status. These rules
  must distinguish frozen history from eligibility for new play.
- Competition has no explicit exceptional-ending state. Stage completion and
  champions currently describe individual stages, including No champion.
- Admin views call commands; public serializers explicitly allowlist fields.
  The public bracket and Changes support English/Vietnamese.

The change reaches models/migrations where needed, command support, all format
progression and qualification paths, correction projections, admin forms and
templates, public API/types/UI/translations, seed fixtures, migration/concurrency
tests, browser journeys, and bracket operating/backlog documents.

## Withdrawal and disqualification

An organizer chooses one competition entrant, a target inactive status, and a
nonblank private reason. Both statuses have the same competitive effects; their
labels and audit intent differ. They do not change the linked registration,
payment, roster, or public identity snapshot.

Always show a server-computed preview before confirmation. Include affected
matches and scores, pending source routes, tie resolutions, Swiss private rounds,
later draws, qualification changes, and any completed-stage outcome affected.
Live matches and already-played dependent results require explicit reset/forfeit
consent. Never infer that consent from a generic submit button.

Apply one atomic transition:

- Preserve previously finalized entered results and historical rows. Removal is
  prospective; retroactive score changes remain explicit result corrections.
- Resolve current published pending matches containing the entrant as forfeits,
  preserving existing real partial scores. With two unavailable sides use a
  double forfeit. Do not manufacture game scores or opponents.
- A live match is resolved only when the preview and confirmation explicitly
  include its forfeit and partial score.
- Exclude the entrant from future active winner/loser routes and qualification.
  Reconcile already-resolved routes so they cannot reintroduce the entrant.
  Preserve historical source wins/losses while resetting affected live/final
  descendants only within the confirmed impact. Normal empty/bye routing still
  waits for all source slots to resolve.
- Later pending elimination matches whose opponent is not yet known remain
  pending until their inputs resolve. Then apply the same inactive-entry rules
  within the result command; attribute any resulting administrative effect to
  the removal that caused it.
- Invalidate affected saved private draws/rounds. Never silently republish or
  redraw. Revalidate published successors against qualification and retire an
  invalid suffix with the existing history-preserving mechanism.
- Draft-only selection changes remain private. First publication and handoff
  publication still require a wholly eligible actual field.

Changing WITHDRAWN to DISQUALIFIED (or vice versa) records the new status/reason
without forfeiting matches twice or replacing the original removal provenance.
Repeated submissions must be rejected as stale or unchanged.

## Qualification and Swiss continuation

Historical standings retain actual scores, opponent contributions and original
seeds. Public entrant availability is separate from a stage's W/L-based Swiss
status; a threshold-qualified entrant can later be withdrawn.

Do not silently promote a lower finisher, change a quota, relax locked rules, or
substitute another registration to compensate for an unavailable qualifier.
Compute the earned cutoff using the configured rules and recorded results,
then exclude unavailable qualifiers. Report a quota shortfall explicitly and
block a normal handoff. Invalidate decisions whose eligibility-dependent inputs
changed; never offer an ineligible contender as a new tie-resolution winner.

For Swiss:

- Keep original entries, starting seeds and the published draw's saved round
  limit. Removing entrants does not recompute that limit from a smaller field.
- Exclude inactive entrants from future pairings and threshold continuation,
  while retaining their earlier results in standings and opponent metrics.
- An active entrant whose registration is no longer approved still blocks new
  publication until an explicit lifecycle decision is made. A recorded inactive
  entrant's historical registration state must not block all remaining players.
- Withdrawal applies from its recorded competition revision and round boundary.
  It must not invalidate earlier published rounds merely because their stored
  fingerprint included the then-active entrant. Current published pairings are
  retained and any affected unplayed match is forfeited; saved private previews
  using the old active field become historical/private and must be regenerated.
- Later input-changing result corrections and restoration still supersede the
  dependent Swiss rounds. Pairing is global, so compare the effective field as
  well as standings inputs at each relevant round boundary.
- Keep explicit minimum-rematch consent and existing bye rules. Do not create
  empty rounds or silently declare a champion when continuation becomes
  impossible; expose the exceptional-ending action and its explanation.

## Restoring an entrant

Restore is a correction, not a direct status toggle. The registration must be
approved for the same division. A closed competition must be reopened first.
Require a private reason and both competition/match change permissions when
published competitive effects are involved.

Record enough provenance during removal and subsequent automatic propagation
to identify the removal's effects: entrant/removal identity, affected match IDs,
before/after competitive state, and the published round boundary. Use existing
ChangeSet history and minimal explicit references where needed; do not rebuild
all operational state by replaying the entire audit log.

The restore preview must:

1. Restore active eligibility and identify still-current forfeits caused by the
   removal, including those applied later when source matches resolved.
2. Undo those effects to their prior pending/live state and real partial scores,
   then recompute against present entrant availability. If the other entrant is
   still unavailable, the match remains an appropriate administrative result.
3. Preserve independently entered results and later explicit corrections.
   A manually corrected result is no longer an untouched removal-generated
   forfeit. Identify it in the preview; do not overwrite it with an old snapshot.
4. Reconcile affected elimination routes, qualification decisions and handoffs;
   include all later played results requiring reset.
5. Supersede affected Swiss rounds from the earliest input boundary changed by
   restoration and all invalid later draws. Regenerate and publish explicitly.
6. Leave already-superseded draws/rounds historical. Restore provenance never
   resurrects an old draw; replacement IDs remain distinct.

Reset only caused dependencies, not unrelated Round Robin results or unaffected
elimination branches. Preserve every pre-restore result in Changes. If an
existing inactive record lacks sufficient authoritative provenance, reject the
undo operation with an actionable explanation rather than invent prior state.

## Exceptional ending and reopening

`End competition here` is a distinct organizer decision on a published source
stage when its qualifying field or the remaining available field cannot complete
the locked continuation. Examples include too few eligible qualifiers, an
impossible locked destination field, or no viable remaining Swiss participants.
It is not a shortcut for skipping unfinished competitive contests or unresolved
ties that could still determine a valid continuation.

The command computes eligible candidates from the source results and actual
availability. An award requires exactly one determinable eligible survivor;
the organizer may award that entrant or end Without a champion. Zero candidates,
multiple candidates, or an unresolved winner permits only Without a champion.
Never infer a champion from seed, row order, an incomplete ranking, or an
eliminated entrant. A Swiss stage itself remains a qualifying stage; any sole
survivor award belongs explicitly to the competition-level exceptional decision.

Add explicit competition-level ending state: source stage, timestamp and optional
awarded entrant. An end timestamp with no awarded entrant means Without a
champion. Validate same-competition references and consistent nullability.
Normal completed stages keep their current meaning; avoid a duplicate general
competition state machine. The reason and exact effects live in ChangeSet.

The preview lists unfinished source contests frozen by the decision and the
entire remaining stage suffix, including every published/played result retired.
Atomically supersede suffix draws and their active tie/round state. Keep original
rows, source results, stage rules and publication timestamps. A previously public
suffix is visibly retired; a wholly private suffix stays private. Source
unplayed contests remain recorded and visibly closed, without fictitious results.

While ended, every competition mutation is blocked except explicit reopening.
This includes entrant actions, draw generation/publication, scoring, scheduling,
rule changes, tie decisions and ordinary result corrections through direct
command/admin calls. Registration remains independently owned; it cannot reopen
or rewrite competition history. Read-only previews/history remain available.

Reopening requires a signed impact preview, both change permissions, explicit
confirmation and a private reason. Clear the exceptional outcome, restore the
source's operational availability, and expose retired later stages as awaiting
replacement (or private draft if never published). It changes neither entrant
availability nor source scores. Keep retired fixtures historical; organizers
must resolve current eligibility/rule blockers and preview/publish new draws.
The locked stage plan stays locked. Ending and reopening each append history.

## Transactions, authorization and privacy

Use the existing lock order: TournamentGame, Competition, then affected records
in stable primary-key order. Preview is read-only. Confirmation locks, verifies
revision, recomputes canonical impact and checks its signed token before writing.
One action commits state/history and increments revision exactly once. Reject
stale/tampered/cross-object tokens and repeated submission without partial effects.

Withdrawal/disqualification requires `change_competition`, plus `change_match`
when published matches are finalized/reset. Restoration follows the same rule
with both permissions for published correction. Ending a wholly unpublished
suffix requires `change_competition`; freezing a live source or retiring published
descendants also requires `change_match`. Reopening always requires both.
Preserve organizer membership, active/staff checks, object scope, CSRF and private
history permissions at every entry point, including superuser command paths.

Public Changes expose allowlisted entrant labels/status transitions, public
match effects, retirement, ending outcome and reopening. Exclude organizer
identity, private reason, private draft IDs, restoration internals, and all
registration/contact/payment data. Historical match snapshots retain the state
at that event; do not rewrite their outcome from current entrant availability.

## Organizer and spectator behavior

Use the existing Entrants workspace for withdrawal, disqualification and restore,
and the existing stage/workspace action and confirmation patterns for end/reopen.
Show status, blocked continuation explanations and the exact effects before the
final confirmation. Existing signed-correction UI is the visual pattern.

Public match cards and standings show withdrawn/disqualified availability
without hiding earlier results. Show the explicit ended outcome, retired-stage
state, and reopening in Changes. Historical match links continue to work.
Keep public EN/VI text, keyboard-accessible controls and page containment at
390px; organizer controls remain English. No new dashboard or visual system.

## Required proof and delivery

Use meaningful focused tests while implementing, then a fresh PostgreSQL
competition/seed gate and affected registration regressions. Cover:

- All five formats; pending/live removal; both unavailable sides; real partial
  scores; double-elimination loser routes and reset finals; byes/empty paths.
- No automatic retroactive results or lower-finisher substitution; exact quota
  shortfalls; tie revalidation; private preview invalidation.
- Swiss next rounds after removal, historical fingerprint stability, threshold
  exits, fixed standings/opponent metrics, consecutive stages and restoration
  after later rounds/descendants have been played.
- Undo provenance, later automatic forfeits, independently corrected results,
  two separate removals affecting one match, unavailable opponents on restore,
  status relabelling, and already-historical fixtures.
- Ending with zero/one/multiple candidates, both public/private suffixes,
  retirement after played descendants, command-wide mutation guards, reopening
  and explicit replacement publication.
- Permission/privacy boundaries, read-only GET, atomic rollback, stale and
  repeated requests, token scope/tampering, and PostgreSQL races against scores,
  publication, restoration, end/reopen and registration eligibility changes.
- A populated upgrade from `0005_swiss` retaining IDs, results, pending and
  superseded ties/rounds, source entries and public history. Document matching
  code/database backup recovery for any migration storing lifecycle decisions.

Extend synthetic development fixtures using commands, preserving rerun identity
and unrelated records. Run focused frontend tests plus Svelte/i18n/build checks
and the complete bracket browser files with lifecycle journeys, English/
Vietnamese public views and 390px checks. Repeat the existing persisted large
Swiss publication measurement if changed fingerprint/validation paths affect it;
do not claim worst-case latency from a solver-only benchmark.

Update the authoritative bracket backlog, project TODO and operating guide with
actual fresh results, exact scope and unresolved limits. Reconcile V1–V5 against
evidence; feature presence or old passing logs alone do not close delivery gates.
No merge or deployment is implied by completing these checks.
