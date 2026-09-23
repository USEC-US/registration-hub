# Section 5: Competition formats delivery plan

Build single elimination → double elimination → TFT → Round Robin → Swiss as
separately usable releases. Organizers operate them through Django admin, with
public brackets and standings in Svelte. All five formats, realtime, and
hardening are required for Full Beta.

This is the delivery plan; each format gets a focused rules specification before
implementation. Complete the required organizer permissions and audit behavior
from the [Section 4 plan](2026-09-23-organizer-registration-operations.md) before
starting dependent competition work.

Source: [TODO Section 5](../../TODO.md#5-bracket-core), its existing TFT and
group-stage requirements, and [General Delivery Plan](../../GENERAL-PLAN.md).

## Action items

- [ ] **5.1 — Deliver single elimination with the shared competition foundation.**
  Add a competition domain linked to existing divisions and organizer-selected
  approved registrations. Support manual seeding, saved random draws, byes,
  private preview, publication, scores, winners, and advancement. Include admin
  controls and the public bracket in this first release. Preserve registration
  snapshots and expose only approved public display fields.

- [ ] **5.2 — Extend elimination to double elimination.** Add upper/lower bracket
  routing, loss tracking, and grand finals. Organizers choose **reset or no reset
  before publication**, and the published rule is locked. Verify both final
  rules, uneven entrant counts, byes, and advancement through both brackets.

- [ ] **5.3 — Deliver TFT lobbies and standings.** Use solo entrants, lobby
  assignments, organizer-controlled shuffling, placement results, configurable
  points, tiebreaks, and Top-X advancement. Support qualification rounds and
  finals. Implement the documented Checkmate behavior: reaching the threshold
  enables a win by placing first in a subsequent game; checked players display
  first and then sort by score; if nobody achieves Checkmate by the game cap, the
  fallback winner comes from total scores across all players. Keep the check
  threshold and maximum game count configurable. Use 8-player lobbies as the
  standard; settle incomplete-lobby handling and exact scoring/tiebreak presets
  in this stage's specification.

- [ ] **5.4 — Deliver Round Robin groups and playoff qualification.** Start with
  a bounded single Round Robin format: group assignment, schedule generation,
  results, standings, scoring/tiebreak rules, and qualification. Handle odd
  group sizes and unresolved ties explicitly. Let organizers preview and confirm
  qualifiers entering an elimination playoff.

- [ ] **5.5 — Deliver a defined Swiss format.** Choose the supported esports
  pairing and tiebreak rules before building the algorithm. Generate each round
  from confirmed previous results; account for byes, withdrawals, repeat
  opponents, and impossible pairings. Allow validated, audited organizer
  overrides. Publish pairings and standings, then support confirmed qualification
  into playoffs.

- [ ] **Apply publication, correction, and audit rules throughout.** Keep drafts
  private and validate entrants and format rules before publication. Record
  result revisions with actor, time, reason, and previous/new values. Preview a
  correction's effect on advancement and standings. Require explicit resolution
  when downstream games have already been played; preserve historical results.
  Commit corrections and derived changes atomically, and reject stale concurrent
  edits.

- [ ] **Verify every format before advancing.** Add focused algorithm and
  PostgreSQL transaction tests, organizer permission checks, public-data privacy
  checks, and a browser journey covering setup → preview → publish → results →
  correction → completion. Include small and uneven fields, byes, duplicate
  entrants, ties, and stage handoffs. Keep public views accessible on mobile.

- [ ] **Reconcile the roadmap and Beta gate.** Update [TODO.md](../../TODO.md)
  and [GENERAL-PLAN.md](../../GENERAL-PLAN.md): incorporate the existing
  TFT/group-stage requirements into Section 5, remove their conflicting
  post-Beta placement, and expand the Beta exit gate to all five formats. Follow
  with Section 6 realtime and Section 7 hardening.

## First implementation slice

Deliver shared competition behavior plus a complete single-elimination workflow.
Settle exact match-scoring rules, forfeits, withdrawals, and correction handling
in that slice's specification.

## Full Beta completion condition

Organizers can set up, publish, operate, correct, and complete all five formats
through Django admin. Public brackets, pairings, and standings expose no private
registration data. Section 6 realtime and Section 7 hardening must also pass
before the release is called Full Beta.
