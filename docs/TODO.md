# Project TODO

## Current state — 2026-09-23

- Public testing is documented at `staging.giaidau.hcmusec.com`; this review did
  not verify the live deployment. The repository includes a Docker/Unfold/Django
  and SvelteKit staging stack plus AMD64/ARM64 image publication to GHCR.
  - Personal testing: Deployment is good, no issues yet. For now: must test
      all available features.
- Account/institution selection, the public catalogue, guest/account registration,
  roster identity snapshots, saved registration stages, private payment proof,
  timed reservations, local VietQR generation, and the receiving-bank catalogue
  are implemented. Full Beta still requires organizer work, brackets, and realtime.
- School is optional at account signup and in the profile, and for each player
  in tournaments without student requirements. Student-only tournaments still
  require each player's student ID and school. The roster form explains the
  HCMUS conduct-point benefit beneath each player form.
- Organizer admin provides combined registration/payment approval, immutable
  roster and contact snapshots, and protected decision history. Payment attempts
  remain visible, but standalone payment review is removed.
- The first organizer navigation slice adds linked division and all-status
  registration totals to tournament/division admin lists and detail pages. These
  are record counts, not capacity counts.
- Organizer registration lists now show role, responsible name, and phone, with
  contact search and division filtering. Detail pages group the private contact
  snapshot, roster, payment attempts, and status history. Authorized organizers
  can view full payment proof images inline; public tournament images fit their
  frames without cropping. Admin record labels identify registrations, roster
  members, payment records, and status events; Vietnamese names display family
  name first. Organizer permission and audit controls are documented below.
- Operational acceptance remains open: verify the receiving destination and scan
  the QR in a bank app, activate/monitor expiry and bank refresh jobs, and verify
  backups and restore procedures. The Compose file does not install these jobs.
- Institution dataset contributions, SePay/account-holder verification, and
  competition formats remain separate unfinished work. Bracket scope and the
  dedicated implementation backlog are tracked in [BRACKET-TODO.md](BRACKET-TODO.md).
- Verification for these registration, organizer UI, and image changes: 290
  Django tests pass on an isolated PostgreSQL 18 instance; server Ruff,
  frontend Svelte checks, and 330 unit/browser component tests pass. This was
  not a full end-to-end browser run, visual review, or live deployment audit.
  No `.env` files or live application data were changed.

## 1. Account and identity foundation

- [x] Finish logout navigation, route behavior, and session tests.
- [x] Implement the existing institution catalogue work.
- [ ] Design a public contribution workflow for the institution dataset, including new schools, corrections, supporting sources, and maintainer review before publication. Keep this separate from the registration flow's "school not found" input; adding a school during registration is not a dataset contribution.
- [x] Replace free-text account school fields with institution selection.
- [x] Allow account signup and profile edits without a school.
- [x] Review sign-in, registration, profile, redirects, and expired-session behavior together.
- [x] Confirm private account information never appears in public APIs.

## 2. Tournament catalogue and public UI

- [x] Finish the responsive public catalogue layout.
  - [x] Replace full-width desktop tournament listings with a 1/2/3-column responsive card grid on both the home page and `/tournaments`.
  - [x] Keep the wide presentation as an optional featured-tournament treatment driven by `is_featured`.
  - [x] Preserve a sensible order for featured and non-featured tournaments without duplicating or hiding tournaments accidentally.
  - [x] Make tournament cards clickable as a whole while preserving accessible link semantics and focus states.
  - [x] Limit the home page to a small preview set of recent or featured tournaments, then add a clear link to view all tournaments.
- [x] Complete the image-ready tournament card contract.
  - [x] Expose and type `cover_image` and `is_featured` consistently across backend API responses and frontend fixtures.
  - [x] Constrain cover image aspect ratio and height so uploaded images cannot overflow or destabilize the layout.
  - [x] Render cover images with localized alt text when present.
  - [x] Omit the image slot entirely when no cover image exists.
  - [x] Preserve useful card metadata in both grid and featured variants, including dates, location, and configured game count.
  - [x] Render the tournament cover image on the tournament detail page when available.
- [x] Improve public tournament UI states.
  - [x] Improve empty states on the home page and `/tournaments` with localized supporting guidance.
  - [x] Defer the tournament-card skeleton until a real client loading path exists, and keep the public pages free of unused skeleton imports.
  - [x] Verify tournament detail states for upcoming, open, closed, and full registration windows remain clear and actionable.
- [x] Audit navigation, tournament detail pages, mobile layout, accessibility, and translations.
  - [x] Add and test active tournament navigation state, including localized route prefixes.
  - [x] Prevent public navigation overflow on narrow mobile screens.
  - [x] Validate all new English and Vietnamese message keys, JSON formatting, and generated Paraglide types.
  - [x] Recheck semantic heading levels, time elements, image alt text, and registration-action visibility.
- [x] Let admins add and edit divisions (TournamentGame) directly inside a tournament.
  - [x] Keep `TournamentGameInline` available from `TournamentAdmin`.
  - [x] Confirm organizer-only admin permissions still gate tournament and division management.
  - [x] Cover the inline configuration with tests or a documented manual smoke check.
- [x] Decide and implement the tournament listing scale behavior.
  - [x] Keep featured tournaments first on the listing page with a stronger highlighted treatment than a normal compact card.
  - [x] Defer pagination to a later catalogue-discovery slice.
  - [x] Keep pagination controls, empty pages, and localized pagination labels out of section 2 because pagination was deferred.
- [x] Add missing section-2 test coverage before marking this section complete.
  - [x] Backend tests for `cover_image` serialization, `is_featured`, featured-first ordering, and admin inline wiring.
  - [x] Frontend tests for `TournamentCard` grid/featured variants, cover fallback, heading levels, listing grids, empty states, nav state, and translations.
  - [x] Update existing `PublicTournament` test fixtures and e2e route mocks with `cover_image` and `is_featured`.
  - [x] Run backend checks/migrations and frontend check/Vitest after the section-2 scope is implemented.
- [x] Defer larger catalogue improvements out of section 2.
  - [x] Public tournament search, filtering, and sorting controls.
  - [x] Image resizing, thumbnail generation, upload preview, cropping, CDN, or production media optimization.
  - [x] A custom organizer tournament-management frontend beyond the Django admin inline.
  - [x] Registration-flow, bracket, payment, and organizer-operations changes covered by later sections.

## 3. Registration journey

- [x] Allow guests to register for tournaments without creating an account.
- [x] Show nonintrusive account-benefit callouts on the sign-in and registration pages.
- [x] Keep the tournament registration form accessible to authenticated accounts.
- [x] Ask whether the submitter is acting as captain or manager for each sign-up.
- [x] Do not add a permanent account role or role database column.
- [x] Link a captain submitter to roster slot 1 for that registration.
- [x] Keep manager submitters outside the roster.
- [x] Collect private captain/responsible-contact information.
- [x] Collect per-player names and date of birth for organizer eligibility review;
  require Student ID and school for student-only tournaments, and keep both
  optional for other tournaments.
- [x] Configure required main roster members and optional substitute places; preserve each submitted player’s role.
- [x] Handle solo entrants consistently.
- [x] Enforce one active entry per claimed player and division, including concurrent submissions. Game-specific identity verification remains deferred.
- [x] Define safe behavior for rejected entries, corrections, and resubmission.
- [x] Keep historical roster and institution snapshots stable.
- [x] Connect roster institution selection to the catalogue and custom-institution fallback.
- [x] Accept payment proof with initial guest submission without an account; keep evidence private.
- [x] Verify captain, manager, solo, guest, signed-in, payment upload, and organizer review against real Django/PostgreSQL. See [verification notes](testing/registration-journey.md).

- [x] Divide registration into automatically saved contact/team, roster, review/submit, and post-submission payment stages, including saved guest return access and expired-entry retry.
- [x] Generate VietQR locally with exact amounts, destination snapshots, and explicit long-transfer-text fallback.
  - [x] Configure the site-wide receiving bank and payment hold in Django admin.
  - [x] Add a local bank catalogue, searchable receiving-bank selection, and a guarded refresh action; see [bank catalogue operations](payments/bank-catalogue.md).
  - [ ] Verify account-holder names automatically; account lookup and SePay remain deferred. Manually entered holder names are explicitly unverified.

## 4. Organizer registration operations

- [x] Show division and registration counts from tournament administration.
- [x] Add direct links from tournaments and divisions to their filtered registrations.
- [x] Improve registration search, filtering, review, payment evidence, and status actions.
  - [x] Search private contact snapshots and filter by role and division; retain
    guarded registration review actions.
  - [x] Show full payment proof images in organizer registration and payment
    details, with protected inline delivery for supported raster formats.
- [x] Show manual review, approval, and rejection controls on registration rows and detail pages for authorized organizers; approving a paid registration also verifies its submitted image proof.
- [x] Display registration, manager/captain, roster, and private contact information
  clearly in organizer tables and detail pages. Tables show role, responsible
  name, and phone; details show all contact channels and the roster snapshot.
- [x] Preserve least-privilege organizer permissions, including both change permissions for combined paid approval.
- [x] Record organizer decisions and bank refreshes in admin history alongside status events and payment reviewer fields.
- [ ] CSV export is deferred until club operations has a concrete need.

## 5. Bracket core

Detailed scope, rule decisions, task dependencies, and completion checks live in
[the bracket core TODO](BRACKET-TODO.md). Update task progress there.
Single and double elimination now have organizer/public workflows and focused
PostgreSQL/browser validation; see the [double-elimination guide](testing/competition-double-elimination.md).
Round robin groups, configurable standings rules and qualification ties now have
organizer/public workflows; see the [round robin guide](testing/competition-round-robin.md).
Swiss and ordered stage handoffs are implemented and workflow-validated; realtime remains open.

Inspiration (and future replacement):

- [Challonge](https://challonge.com)
- [Toornament](https://toornament.com)
- [Battlefy](https://battlefy.com)
- [Garena Arena of Valor VN Community Tournament hosting site](https://congdong.lienquan.garena.vn)

Agreed scope:

- Agreed formats: single elimination, double elimination, single/double round robin groups,
  and both fixed-round and win/loss-threshold Swiss, combined into ordered stages
  with TO-confirmed advancement.
- Support best-of series and fixed-game series with draws for round robin and
  fixed-round Swiss.
- Organizer controls stay in Django Unfold admin; public SvelteKit brackets,
  schedules, pairings, standings, and Changes are read-only. TO identities and
  internal correction notes remain private.
- Implement through small tasks with explicit dependencies and file ownership
  so independent subagent work can run in parallel.
- TFT is scheduled next as Section 5.1; live updates remain Section 6.

## 5.1. TFT tournament engine — next priority

Deliver immediately after Section 5, before Section 6 realtime work, because TFT
tournaments are a near-term club need. TFT uses 8-player lobbies and placement
points, not head-to-head bracket matches. Reuse approved entrants, ordered
stages, organizer permissions, publishing, and correction/audit foundations
without forcing lobbies into the elimination or win/loss Swiss data models.

First usable slice:
- [ ] Solo registration: exactly one player per entry; select approved players as entrants.
- [ ] Create and operate 8-player lobbies with manual/random assignments and organizer corrections.
- [ ] Define policy for fields not divisible by eight, withdrawals, and replacements
  before publishing lobby assignments.
- [ ] Record each player's placement for every game; support configurable placement
  points, fixed-game (BoX) series, cumulative standings, and tiebreakers.
- [ ] Advance configurable Top-N players per lobby or overall to subsequent
  qualification stages and finals, requiring TO confirmation.
- [ ] Support Checkmate finals with configurable threshold and maximum games:
  - Checked players display above unchecked players, then sort by points.
  - A checked player must finish first in a subsequent game to win.
  - If the game limit is reached without a Checkmate winner, award the title
    using total points and the configured tiebreakers.
- [ ] Publish read-only lobbies, results, standings, and progression in SvelteKit;
  keep operations in Django Unfold.
- [ ] Preserve result history and safely recalculate scores, qualification,
  and champion status after authorized corrections.

Follow-on competitive options:
- [ ] Snake seeding and standings-based (Swiss-style) lobby reseeding; keep
  this separate from the existing win/loss Swiss bracket format.
- [ ] Progressive elimination, wildcard qualification, and configurable
  point carryover or reset between stages.
- [ ] Evaluate Double Up and 4v4 separately because they require team entrants.

TFT is prioritized in the implementation order, but is not automatically a
Full Beta exit-gate blocker.

## 6. Realtime competition experience

- [ ] Add Django Channels and ASGI routing.
- [ ] Add Redis-backed channel layers for multi-process operation.
- [ ] Broadcast published bracket, score, result, and advancement changes.
- [ ] Keep organizer mutations in authenticated HTTP/admin commands; public sockets should be read-only.
- [ ] Make clients reload an authoritative snapshot after reconnecting or missing events.
- [ ] Test multiple tabs, reconnects, unauthorized connections, and concurrent updates.
- [ ] Add realtime connection states without making the bracket unusable when sockets fail.

## 7. Full Beta hardening

- [ ] Maintain green backend, frontend, type, lint, and migration checks throughout every slice.
- [x] Add true full-stack registration browser tests against Django, not only mocked API routes; see [existing journey coverage](testing/registration-journey.md). Single/double-elimination journeys are also covered; realtime journeys remain open.
- [ ] Complete realistic captain/manager/solo/payment fixture coverage. Single- and
  double-elimination fixtures are delivered; see the [seed guide](testing/competition-double-elimination.md).
- [ ] Test all participant and organizer permissions.
- [ ] Audit contact information and payment-file privacy.
- [ ] Validate file types, upload limits, rate limits, and error handling.
- [ ] Review JWT/session security before exposing the beta to real people.
- [ ] Run responsive and accessibility checks on participant and organizer workflows.
- [ ] Prepare a staging-like environment with PostgreSQL, Redis, media storage, logs, and backups.
- [ ] Give club members and managers an end-to-end testing checklist.
- [ ] Record feedback and classify blockers separately from later improvements.

## Full Beta exit gate

Full Beta is ready when club staff can:

- Configure and publish a tournament and its divisions.
- Accept and review real registrations.
- Distinguish managers from captains per registration.
- Review captain contact and payment evidence safely.
- Build, seed, publish, and operate single/double elimination, round robin groups,
  and both Swiss presets, including qualification into playoffs.
- Enter and correct results while public viewers receive realtime updates.
- Complete these workflows without critical permission, privacy, data-loss, or usability failures.

  SePay and TFT are not Full Beta blockers.

## 8. Stabilization

- [ ] Triage beta feedback and close critical workflow, security, and data-loss blockers.
- [ ] Add regression coverage for important fixes and rerun participant/organizer journeys.
- [ ] Confirm that entrant, result, publication, correction, and audit workflows
  remain reliable before production rollout.

## 9. Post-Beta: SePay integration

- [ ] Confirm SePay’s current API, webhook, sandbox, and reconciliation contracts.
- [ ] Add provider payment attempts without removing manual payment evidence.
- [ ] Verify webhook authenticity and process events idempotently.
- [ ] Match transfers safely and expose unresolved payments to organizers.
- [ ] Preserve manual correction and reconciliation workflows.
- [ ] Test duplicate, delayed, missing, and malformed provider events.
- [ ] Do not automatically approve tournament eligibility merely because payment succeeded.

## 10. Production deployment

Staging groundwork exists: Compose services, persistent database/media volumes,
SWAG reverse-proxy configuration, and multi-architecture GHCR image builds.
Container CI currently builds/publishes images; it does not run the full test/lint
suite or prove production readiness. The production items below remain open.

- [ ] Select hosting for the Svelte frontend, Django ASGI application, PostgreSQL, Redis, and media.
- [ ] Configure domains, HTTPS, trusted origins, secrets, and production email.
- [ ] Establish CI checks, migration gates, rollback procedures, and staged releases.
- [ ] Configure durable media storage, database backups, and restore testing.
- [ ] Add centralized logs, health checks, error reporting, and operational alerts.
- [ ] Write organizer and incident-response runbooks.
- [ ] Conduct a final security, privacy, performance, and production-readiness review.
- [ ] Roll out gradually after Full Beta and SePay acceptance.
