# General Delivery Plan

This is the short execution guide for the work listed in
[TODO.md](./TODO.md). It describes direction and completion conditions, not
file-level implementation tasks.

## How to work each phase

1. Inspect the affected flow and its dependencies with CodeGraph.
2. Settle only the decisions needed for the current phase.
3. Define acceptance cases and add focused tests.
4. Build one complete backend-to-UI slice at a time.
5. Verify permissions, failure states, and existing behavior.
6. Demonstrate the finished flow and update the TODO.

Do not start a dependent phase while its required behavior is unstable.

## Delivery path

```text
Accounts → Public UI → Registration → Organizer tools → Brackets
    → Live updates → Full Beta → Stabilization
                                  ├─ TFT → Round Robin → Swiss
                                  └─ SePay → Production
```

## Full Beta

### 1. Account and identity foundation

**Direction:** Connect the existing logout behavior to the visible application
shell, finish the approved institution catalogue flow, and make authentication
and permissions predictable. Identify abuse-sensitive public actions and add
Cloudflare Turnstile at the selected entry points. Require trusted server-side
verification before the existing action runs, and keep secrets out of the
browser.

**Move on when:** Login, logout, expiry, redirects, institution selection, and
protected pages work consistently for participants and organizers. Protected
forms accept valid Turnstile challenges, reject invalid or replayed tokens, and
provide an accessible retry path.

### 2. Public tournament UI

**Direction:** Refactor the shared tournament presentation into a responsive
card grid. Add a separate featured style and leave a clean place for future
cover images.

**Move on when:** The root and tournament-list pages are consistent, readable,
accessible, and usable at common mobile and desktop sizes.

### 3. Registration flow

**Direction:** Put the captain/manager relationship and captain contact on each
registration, never on the user account. Enforce roster rules in backend
services first, then expose them through a form that remains reachable,
explains every available next action, and preserves manual payment evidence.

**Move on when:** A captain is linked to slot 1, a manager remains outside the
roster, valid roster sizes submit correctly, existing registrations remain
understandable, and conflicting player claims are rejected safely.

### 4. Organizer and admin operations

**Direction:** Add inline division creation, direct registration links and
counts, strong filters, clear review actions, private-data permissions,
exports, and audit records.

**Move on when:** An organizer can configure divisions and handle all
registrations for either a tournament or one division without searching
through unrelated admin pages.

### 5. Bracket system

**Direction:** Start with organizer-selected approved entrants, manual or
random seeding, byes, and a preview. Complete Single Elimination first, then
reuse the match and result flow for Double Elimination. Add publishing,
corrections, audit history, and a public view.

**Move on when:** Organizers can create, publish, score, correct, and finish
both bracket formats without corrupting advancement or historical results.

### 6. Live updates

**Direction:** Add Django Channels only after bracket HTTP behavior is stable.
Send small change notifications through WebSockets, refetch authoritative
data, and use Redis for the production channel layer.

**Move on when:** Public bracket views update promptly, reconnect cleanly, and
still work through normal HTTP when WebSockets are unavailable.

### 7. Full-beta hardening

**Direction:** Add browser coverage for complete participant and organizer
journeys, realistic seed data, security and privacy checks, responsive review,
and a staging-like beta environment.

**Move on when:** Club members and managers pass the exit gate in TODO.md
without critical permission, privacy, reliability, or data-loss failures.

### 8. Stabilization

**Direction:** Classify beta feedback by severity, reproduce each important
issue, add a failing test where practical, fix the cause, and rerun the full
critical journey.

**Move on when:** Beta blockers are closed and the shared entrant, result,
publishing, correction, and audit behavior is stable enough to extend.

## Competition Expansion

### 9. TFT

**Direction:** Build a lobby-and-standings format that shares entrants and
published results with the core system but does not pretend to be a bracket
tree. Add solo entry, 8-player lobby assignment, configurable points, Top-X
advancement, Checkmate, and organizer corrections.

**Move on when:** A large solo field can progress through multiple lobbies to
a final, including a Checkmate win or the maximum-game points fallback.

### 10. Round Robin

**Direction:** Add a bounded Round Robin preset with schedule generation,
result entry, configurable scoring and tiebreaks, standings, organizer
corrections, and playoff qualification.

**Move on when:** A complete group produces reproducible standings and the
correct approved entrants can enter a playoff.

### 11. Swiss

**Direction:** Choose the supported Swiss preset before coding it. Then add
round-by-round pairing, bye and repeat-opponent handling, standings,
tiebreaks, organizer overrides, and playoff qualification.

**Move on when:** Every new round can be generated from confirmed prior
results and corrections do not leave later pairings inconsistent.

## Release Readiness

This branch starts from the stabilized beta and does not wait for every
advanced competition format.

### 12. SePay

**Direction:** Recheck current provider documentation, isolate SePay behind a
payment boundary, verify and deduplicate webhooks, add reconciliation tools,
and preserve manual payment handling.

**Move on when:** Sandbox payment flows cover success, delay, duplication,
underpayment, mismatch, and recovery without automatically granting tournament
eligibility.

### 13. Production deployment

**Direction:** Prepare the ASGI application, frontend, PostgreSQL, Redis, media
storage, secrets, email, migrations, backups, monitoring, and rollback
procedures. Release in controlled stages.

**Move on when:** A production-like deployment passes smoke and recovery tests,
organizers have operating instructions, and the service can be monitored and
rolled back safely.

## Decisions deferred to their phase

- Double Elimination grand-final reset behavior.
- TFT point presets and fallback tiebreak sequence.
- The exact supported Swiss pairing and tiebreak preset.
- The Turnstile-protected entry points, environment domains, and verification
  deployment.
- SePay’s current API details and the final hosting platform.
