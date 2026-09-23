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
- Organizer admin already provides registration/payment review actions, immutable
  roster and contact snapshots, and registration status history. Section 4 tracks
  the remaining usability and audit review, not a replacement implementation.
- The first organizer navigation slice adds linked division and all-status
  registration totals to tournament/division admin lists and detail pages. These
  are record counts, not capacity counts.
- Organizer registration lists now show role, responsible name, and phone, with
  contact search and division filtering. Detail pages group the private contact
  snapshot, roster, payment attempts, and status history. Authorized organizers
  can view full payment proof images inline; public tournament images fit their
  frames without cropping. Admin record labels identify registrations, roster
  members, payment records, and status events; Vietnamese names display family
  name first. Further audit and permissions review remains open.
- Operational acceptance remains open: verify the receiving destination and scan
  the QR in a bank app, activate/monitor expiry and bank refresh jobs, and verify
  backups and restore procedures. The Compose file does not install these jobs.
- Institution dataset contributions, SePay/account-holder verification, and
  competition formats remain separate unfinished work. Settle the expanded bracket
  scope noted in section 5 before implementation.
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
    existing guarded review and payment actions.
  - [x] Show full payment proof images in organizer registration and payment
    details, with protected inline delivery for supported raster formats.
- [x] Show manual review, approval, and rejection controls on registration rows and detail pages for authorized organizers; keep payment proof verification separate.
- [x] Display registration, manager/captain, roster, and private contact information
  clearly in organizer tables and detail pages. Tables show role, responsible
  name, and phone; details show all contact channels and the roster snapshot.
- [ ] Preserve least-privilege organizer permissions.
- [ ] Add an audit trail for consequential organizer actions.
- [ ] Consider safe CSV export if club operations require it.

## 5. Bracket core

- [ ] Support single elimination.
- [ ] Support double elimination.
- [ ] Explicitly defer groups, round robin, Swiss, and other pairing systems.
  - It's now possible to de-defer this, and start working on it as part of a full core bracket system.
  - This also means we should think of putting the TFT system here too. Complex (itself has a ton of rules) but TFT is popular these days in the Student community.
- [ ] Let organizers select entrants from approved registrations.
- [ ] Support manual seeding, randomization, byes, preview, and publication.
- [ ] Track rounds, matches, sides, scores, winners, and advancement.
- [ ] Support organizer result entry and controlled correction of mistakes.
- [ ] Preserve an audit history when published results change.
- [ ] Decide the double-elimination grand-final reset rule when this slice begins.
- [ ] Expose public brackets and results without private registration data.

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
- [x] Add true full-stack registration browser tests against Django, not only mocked API routes; see [existing journey coverage](testing/registration-journey.md). Bracket/realtime journeys remain to be added with those features.
- [ ] Seed realistic captain, manager, solo, payment, single-elimination, and double-elimination scenarios.
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
- Build, seed, publish, and operate single- or double-elimination brackets.
- Enter and correct results while public viewers receive realtime updates.
- Complete these workflows without critical permission, privacy, data-loss, or usability failures.

  SePay and group-stage formats are not Full Beta blockers.

### 8. TFT — early post-beta

- Solo registration: exactly one player per entry.
- Split large player pools into 8-player lobbies.
- Organizer-controlled shuffling, lobby assignment, and corrections.
- Configurable advancement rules such as Top 4 or Top 2.
- Support multi-round qualification followed by playoffs/finals.
- Configurable point tables and tiebreak rules.
- Checkmate finals:
  - Configurable check threshold X—for example, 20 points.
  - Checked players display above unchecked players, then sort by score.
  - A checked player wins by placing first in a subsequent game.
  - Configurable maximum Y games—such as 8.
  - If nobody achieves Checkmate, the highest total score across all players wins.

- Preserve result history and recalculate standings safely after organizer corrections.

### 9. Group stages — later post-beta

- Round Robin first.
- Swiss afterward.
- Configurable rounds, scoring, tiebreaks, advancement count, and playoff handoff.
- Organizer-controlled pairings and corrections where required.
- Limit this to supported esports presets rather than attempting every possible group-stage variation.

## 10. Post-Beta: SePay integration

- [ ] Confirm SePay’s current API, webhook, sandbox, and reconciliation contracts.
- [ ] Add provider payment attempts without removing manual payment evidence.
- [ ] Verify webhook authenticity and process events idempotently.
- [ ] Match transfers safely and expose unresolved payments to organizers.
- [ ] Preserve manual correction and reconciliation workflows.
- [ ] Test duplicate, delayed, missing, and malformed provider events.
- [ ] Do not automatically approve tournament eligibility merely because payment succeeded.

## 11. Production deployment

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
