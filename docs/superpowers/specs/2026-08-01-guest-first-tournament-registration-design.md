# Guest-First Tournament Registration Design

## Context

Section 3 moves tournament registration from account-required to account-optional. The current backend requires `Registration.submitted_by` and the current frontend redirects unauthenticated visitors away from the registration page. The club's preferred workflow is different: guests should be able to submit tournament registrations, while signed-in users should still get convenience benefits.

Current roster sizing already belongs to `TournamentGame` through `team_size_min` and `team_size_max`, and the registration service validates those limits. Section 3 should preserve that model so team games and solo games use the same constraints.

## Goals

- Allow unauthenticated visitors to submit tournament registrations.
- Keep signed-in registration fully supported and beneficial without making accounts mandatory.
- Ask each submitter whether they are acting as captain or manager for that registration.
- Avoid adding a permanent account role or global role column.
- Link a captain submitter to roster slot 1 for that registration.
- Keep manager submitters outside the roster.
- Collect private responsible-contact information for every registration.
- Support actual `team_size_min` and `team_size_max` constraints, including solo divisions with min 1 and max 1.
- Enforce one active roster claim per player and division as far as the collected roster identity allows.
- Define rejected, correction, and resubmission behavior.
- Keep historical roster, institution, and contact snapshots stable.

## Non-Goals

- No guest self-service edit flow in this slice.
- No email magic-link correction flow in this slice.
- No permanent captain or manager role on accounts.
- No public exposure of Facebook, phone, email, Discord, or payment evidence.
- No guest-safe payment-proof upload flow in this slice. Existing account-owned payment evidence can stay account-only until the organizer/payment slice designs a guest-safe path.

## Product Decisions

Registration is guest-first and locked after submission. Guests can submit without creating an account. If they make a mistake, they contact organizers through the existing club contact channels, matching the previous Google Forms workflow.

Signed-in users use the same registration form. The UI may show quiet account-benefit callouts for guests, but those callouts must not block or interrupt registration. Benefits can include easier future registration, saved profile data later, and account-visible registration history.

Every registration has a per-registration submitter role:

- `captain`: the submitter is a roster player, and roster slot 1 is the captain.
- `manager`: the submitter is not a roster player, and manager details are collected outside the roster.

Roster sizing is always based on player count only. Captains count as players. Managers do not count as players. A solo game is represented by `team_size_min = 1` and `team_size_max = 1`, not by a separate solo-only flow.

## Data Model

`Registration.submitted_by` becomes nullable. It remains populated when an authenticated user submits and stays empty for guest submissions.

`Registration` gains a per-registration submitter role with two values: `captain` and `manager`.

`Registration` stores a private responsible-contact snapshot:

- Facebook: required.
- Phone: required.
- Email: optional.
- Discord: optional.

The contact fields are operational data for organizers. They must appear in admin/organizer views that need them, but must not appear in public tournament APIs.

Manager submissions need a manager display name or handle separate from the roster. Captain submissions can derive the responsible person from roster slot 1 and attach the contact snapshot to that registration.

Roster member snapshots remain stable. Later account, profile, institution, or roster edits must not rewrite historical registration data.

## Backend Flow

The registration submit action accepts both authenticated and unauthenticated requests. Authentication remains useful: when a valid JWT is present, the created registration records `submitted_by`; when no user is authenticated, the registration is created as a guest submission.

List, detail, and payment-attempt routes remain protected unless separately redesigned. Guest submissions do not receive account-dashboard access in this slice.

The registration serializer accepts:

- tournament game id
- team name
- submitter role
- responsible-contact fields
- manager display name or handle when role is `manager`
- roster members
- Turnstile token

The service validates:

- tournament is published
- registration window is open
- capacity is available
- roster size is between `team_size_min` and `team_size_max`
- exactly one captain exists in the roster
- captain submitter means roster slot 1 is captain
- manager submitter means the manager is outside the roster
- team name exists exactly for team games
- display order starts at 1, is unique, and is contiguous
- required player snapshots are present
- required contact fields are present
- one active roster claim per player and division

Active duplicate checks should treat `SUBMITTED`, `UNDER_REVIEW`, and `APPROVED` as active. `REJECTED` entries are inactive for duplicate checks so a corrected resubmission can be accepted.

Because guests do not have account identity, player duplicate checks should use the roster identity captured by the form. The first implementation can enforce a normalized roster claim per tournament game using the player-identifying fields currently collected, then tighten that model later if the club adds stronger player identifiers.

`RegistrationStatusEvent.actor` should allow empty actor values for guest-created events. Organizer actions continue recording the organizer actor.

## Frontend Flow

The tournament registration page no longer redirects unauthenticated visitors on mount. It renders the same form for guests and signed-in users.

The form flow:

1. Select submitter role: captain or manager.
2. For captain submissions, slot 1 is labeled as captain and collects player details.
3. For manager submissions, show a manager detail/contact section before the roster.
4. Collect Facebook and phone as required private contact fields.
5. Collect email and Discord as optional private contact fields.
6. Render roster controls that respect `team_size_min` and `team_size_max`.
7. Require Turnstile before submit.
8. Show a confirmation after submit explaining that corrections require contacting organizers.

Guest account-benefit callouts can appear on the registration page and sign-in page, but they should be small, contextual, and non-blocking.

Authenticated users should still be able to submit with the same form. Account-specific conveniences, such as profile prefill, can come later.

## Error Handling

Validation errors should map to the relevant form fields when possible. Roster-size, captain-role, and duplicate-player errors should be visible near the roster. Contact errors should appear near the contact section.

Unauthenticated submission must not produce a sign-in redirect. Authentication errors should only affect account-only routes or signed-in-only follow-up flows.

Turnstile failures should preserve form input and ask for a fresh challenge token.

Successful guest submissions should avoid account-only next steps. They should show the registration summary and organizer correction instructions.

## Testing

Backend tests should cover:

- guest registration can submit without `submitted_by`
- authenticated registration still records `submitted_by`
- contact field requirements
- captain submitter links to roster slot 1
- manager submitter stays outside the roster
- `team_size_min` and `team_size_max` are enforced for team and solo games
- duplicate active roster claims are rejected within a division
- rejected entries allow corrected resubmission
- private contact fields do not appear in public serializers

Frontend tests should cover:

- guest visitors stay on the registration page instead of being redirected
- submitter role toggles captain/manager form sections
- captain slot 1 behavior
- roster add/remove limits for min and max players
- required Facebook and phone validation
- optional email and Discord fields
- guest submission sends no access token and succeeds
- signed-in submission keeps the authenticated path
- confirmation copy explains locked submissions and organizer corrections
- account-benefit callouts stay non-blocking

Run Django registration tests, migration checks, Svelte checks, and focused Vitest coverage before marking Section 3 items complete.
