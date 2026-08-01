# Project TODO

## 1. Account and identity foundation

- [x] Finish logout navigation, route behavior, and session tests.
- [x] Implement the existing institution catalogue work.
- [x] Replace free-text account school fields with institution selection.
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
- [ ] Audit navigation, tournament detail pages, mobile layout, accessibility, and translations.
  - [ ] Add and test active tournament navigation state, including localized route prefixes.
  - [ ] Prevent public navigation overflow on narrow mobile screens.
  - [ ] Validate all new English and Vietnamese message keys, JSON formatting, and generated Paraglide types.
  - [ ] Recheck semantic heading levels, time elements, image alt text, and registration-action visibility.
- [ ] Let admins add and edit divisions (TournamentGame) directly inside a tournament.
  - [ ] Keep `TournamentGameInline` available from `TournamentAdmin`.
  - [ ] Confirm organizer-only admin permissions still gate tournament and division management.
  - [ ] Cover the inline configuration with tests or a documented manual smoke check.
- [ ] Decide and implement the tournament listing scale behavior.
  - [ ] Keep featured tournaments first on the listing page with a stronger highlighted treatment than a normal compact card.
  - [ ] Decide whether pagination belongs in section 2 now or should move to a later catalogue-discovery slice.
  - [ ] If pagination stays in section 2, cover the backend response contract, frontend controls, empty pages, and localized labels with tests.
- [ ] Add missing section-2 test coverage before marking this section complete.
  - [x] Backend tests for `cover_image` serialization, `is_featured`, featured-first ordering, and admin inline wiring.
  - [ ] Frontend tests for `TournamentCard` grid/featured variants, cover fallback, heading levels, listing grids, empty states, nav state, and translations.
  - [x] Update existing `PublicTournament` test fixtures and e2e route mocks with `cover_image` and `is_featured`.
  - [ ] Run backend checks/migrations and frontend check/Vitest after the section-2 scope is implemented.
- [ ] Defer larger catalogue improvements out of section 2.
  - [ ] Public tournament search, filtering, and sorting controls.
  - [ ] Image resizing, thumbnail generation, upload preview, cropping, CDN, or production media optimization.
  - [ ] A custom organizer tournament-management frontend beyond the Django admin inline.
  - [ ] Registration-flow, bracket, payment, and organizer-operations changes covered by later sections.

## 3. Registration journey

- [ ] Keep the tournament registration form accessible to authenticated accounts.
- [ ] Ask whether the submitter is acting as captain or manager for each sign-up.
- [ ] Do not add a permanent account role or role database column.
- [ ] Link a captain submitter to roster slot 1 for that registration.
- [ ] Keep manager submitters outside the roster.
- [ ] Collect private captain contact information.
- [ ] Support actual minimum/maximum roster sizes instead of always forcing the maximum.
- [ ] Handle solo entrants consistently.
- [ ] Enforce one active entry per claimed player and division.
- [ ] Define safe behavior for rejected entries, corrections, and resubmission.
- [ ] Keep historical roster and institution snapshots stable.

## 4. Organizer registration operations

- [ ] Show division and registration counts from tournament administration.
- [ ] Add direct links from tournaments and divisions to their filtered registrations.
- [ ] Improve registration search, filtering, review, payment evidence, and status actions.
- [ ] Display manager, captain, roster, and private captain-contact information clearly.
- [ ] Preserve least-privilege organizer permissions.
- [ ] Add an audit trail for consequential organizer actions.
- [ ] Consider safe CSV export if club operations require it.

## 5. Bracket core

- [ ] Support single elimination.
- [ ] Support double elimination.
- [ ] Explicitly defer groups, round robin, Swiss, and other pairing systems.
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
- [ ] Add true full-stack browser tests against Django, not only mocked API routes.
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

- [ ] Select hosting for the Svelte frontend, Django ASGI application, PostgreSQL, Redis, and media.
- [ ] Configure domains, HTTPS, trusted origins, secrets, and production email.
- [ ] Establish CI checks, migration gates, rollback procedures, and staged releases.
- [ ] Configure durable media storage, database backups, and restore testing.
- [ ] Add centralized logs, health checks, error reporting, and operational alerts.
- [ ] Write organizer and incident-response runbooks.
- [ ] Conduct a final security, privacy, performance, and production-readiness review.
- [ ] Roll out gradually after Full Beta and SePay acceptance.
