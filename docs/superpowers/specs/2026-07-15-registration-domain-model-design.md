# Registration domain model design (v1)

**Status:** approved design
**Date:** 2026-07-15

## Purpose

Define the first durable data model for a multi-tournament esports registration hub. This document is the domain contract for Django models, Django REST Framework endpoints, and the SvelteKit client; it is not a line-by-line substitute for `models.py`.

This design supersedes the organizer-surface decision in [the earlier Phase 0 notes](../../2026-07-14-spec.md): Django Admin is allowed as the v1 internal organizer console. All public and participant-facing experiences are built in SvelteKit.

## Scope and non-goals

This phase covers accounts, tournaments, divisions, registrations, player rosters, manual payment evidence, and review history.

It intentionally does not model:

- persistent teams or free-agent/team-matching;
- schedules, brackets, matches, or results;
- payment-gateway integration;
- automated student-ID, school, or professional-player verification;
- per-tournament organizer assignment;
- a participant-facing withdrawal or amendment workflow.

Those features must be added as explicit follow-up designs rather than inferred from this schema.

## System boundary

| Surface | Responsibility |
| --- | --- |
| SvelteKit | Public tournament information, authentication UI, profile defaults, registration submission, payment-proof upload, and "My Registrations." |
| Django REST Framework | Authoritative validation, permissions, transactional commands, and public/read serializers. |
| Django Admin | Trusted internal organizer work: catalog management, registration review, payment review, and status actions. |

Django Admin is an operations tool, not a participant-facing product surface. Admin actions must invoke the same domain services as the API; organizers must not freely edit status fields and bypass business guards.

## Vocabulary

- **Tournament:** an event with public information and one or more divisions.
- **Division:** one playable category within a tournament and game. It owns registration dates, capacity, team-size limits, and fee.
- **Registration:** one submitted entry into a division, owned operationally by the account that submitted it.
- **Registration member:** an actual player in a registration. It exists for both solo and team registrations.
- **Submitter:** the authenticated account responsible for the registration. A submitter may be a captain or a non-playing manager.
- **Snapshot:** public player data copied at registration time so past tournaments do not change when a profile changes.

## Entity map

```text
User ── submits ──< Registration >── Division ──> Tournament
                           │              │
                           │              └──> Game
                           │
                           ├──< RegistrationMember >── User? (claimed player)
                           ├──< PaymentAttempt
                           └──< RegistrationStatusEvent
```

`RegistrationMember` is a uniform roster record. A solo registration has exactly one member; a team registration has the configured number of members. There is no separate `Team` model in v1.

## Model contracts

### `accounts.User`

Use a custom user model from the first migration. It uses a unique email address as its login identifier and has the normal Django staff and superuser flags.

| Field | Rule |
| --- | --- |
| `email` | Required and unique; the login identifier. |
| `gamer_tag` | Live profile default used to prefill a new registration. It is not globally unique. |
| `school` | Live profile default used to prefill a new registration. |

Set `AUTH_USER_MODEL` before migrations are created. Do not store a "formerly known as" list on the user; it is derived from historical member snapshots.

### `tournaments.Game`

A reusable catalog item with `name`, unique `slug`, and `is_active`.

### `tournaments.Tournament`

The event identity and general public information: `name`, unique `slug`, description, optional start/end times, optional location/online details, and publication state.

### `tournaments.Division`

Joins a tournament and game and owns all registration-specific configuration.

| Field | Rule |
| --- | --- |
| `tournament`, `game` | Required foreign keys. A tournament may contain more than one division for the same game. |
| `name`, `slug` | Division label and a slug unique within its tournament. |
| `team_size_min`, `team_size_max` | Positive integers. Individual means both are `1`; team means `team_size_max > 1`. |
| `registration_opens_at`, `registration_closes_at` | Timezone-aware timestamps; opens before closes. |
| `registration_capacity` | Nullable positive integer. It counts registrations (solo entrants or teams), not individual roster seats. |
| `fee_amount`, `fee_currency` | Non-negative `Decimal` and ISO currency code. Zero means no payment is required. |

Do not persist an `is_team` flag: it is derived from the team-size fields. Do not make `(tournament, game)` unique, because a game can later have distinct open, novice, or other divisions.

### `registrations.Registration`

The current state of a division entry.

| Field | Rule |
| --- | --- |
| `division` | Required division being entered. |
| `submitted_by` | Required account responsible for the entry; it does not imply that the user is a player. |
| `team_name` | Required for a team division and empty for an individual division. It belongs here until a real reusable `Team` model is needed. |
| `status` | One of `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, or `REJECTED`. |
| `fee_amount_snapshot`, `fee_currency_snapshot` | Copied from the division at submission time; later division-fee edits cannot rewrite history. |
| `submitted_at`, `created_at`, `updated_at` | Audit timestamps. |

There is no `DRAFT` state in v1. The frontend holds unfinished form data locally; a database registration is created when the entry is submitted. There is also no generic direct-edit endpoint after submission. Future amendment or withdrawal behavior must be introduced as explicit commands and states.

### `registrations.RegistrationMember`

Represents every actual player, including the sole player in an individual division.

| Field | Rule |
| --- | --- |
| `registration` | Required parent registration. |
| `user` | Nullable account link. Null represents an unclaimed, free-text roster entry. |
| `gamer_tag_snapshot`, `school_snapshot` | Required public display data captured for this tournament entry. |
| `is_captain` | Exactly one member is captain when the registration is submitted; the sole member of a solo registration is its captain. |
| `display_order` | Stable roster ordering for public rendering. |

The submitted account may be absent from the roster when acting as a manager. Do not place public snapshot fields only on `User`; historical public displays must use these fields.

### `registrations.PaymentAttempt`

Keeps payment activity separate from the registration state.

| Field | Rule |
| --- | --- |
| `registration` | Required parent registration. |
| `method` | Starts with `MANUAL_PROOF`; future provider methods can be added without changing `Registration`. |
| `status` | `PENDING`, `VERIFIED`, or `REJECTED`. |
| `amount`, `currency` | The amount represented by this attempt. |
| `proof_file`, `reference` | Manual evidence and transfer reference where applicable. A provider attempt can instead use its provider reference. |
| `reviewed_by`, `reviewed_at`, `review_note` | Set only by organizer review. |
| `created_at` | Submission timestamp. |

No payment attempt is required for a zero-fee registration. A rejected manual proof remains in history; a corrected proof creates a new attempt. Verifying a payment does not automatically approve the registration.

### `registrations.RegistrationStatusEvent`

An append-only audit record for a status transition.

| Field | Rule |
| --- | --- |
| `registration` | Required parent registration. |
| `from_status`, `to_status` | The attempted state transition; the initial submission has no previous status. |
| `actor` | The user who performed the action, when applicable. |
| `note` | Optional organizer explanation. |
| `created_at` | Immutable event time. |

`Registration.status` is the efficient current state; events preserve why and by whom it changed.

## Snapshots and public identity

At submission time, the system copies each player’s gamer tag and school into `RegistrationMember`. The profile values on `User` remain live defaults only.

Public player displays use the snapshot as a title/subtitle pair:

```text
GamerTag
School
```

"Formerly known as" is derived, not stored: query distinct approved member snapshots for the same claimed user and game, order them by registration time, and exclude the user’s current gamer tag. Scoping through `registration.division.game` avoids mixing identities from unrelated games.

## Invariants and guards

### Database constraints

- `Game.slug` and `Tournament.slug` are unique.
- `Division.slug` is unique within a tournament.
- `team_size_min >= 1` and `team_size_max >= team_size_min`.
- `registration_opens_at < registration_closes_at`.
- `registration_capacity` is either null or greater than zero.
- Fees are non-negative decimals.
- At most one `RegistrationMember` per registration has `is_captain=True`, implemented with a conditional unique constraint.

Database constraints protect facts local to one row or table. They cannot safely enforce capacity, roster count, or duplicate claimed players across related registrations.

### Transactional domain commands

All cross-record rules live in backend services and run inside database transactions. SvelteKit form validation and serializer validation may provide early feedback but are never authoritative.

| Command | Required guard behavior |
| --- | --- |
| `submit_registration` | Lock the division; verify its registration window and remaining capacity; validate team name, roster count, and exactly one captain; prevent a claimed player from having another active registration in that division; snapshot the fee and player display data; create the registration, members, and initial status event atomically. |
| `claim_registration_member` | Lock the division; ensure the account is not already a claimed active member in that division; then attach the account to the roster entry. |
| `start_review` | Organizer-only transition from `SUBMITTED` to `UNDER_REVIEW`, with a status event. |
| `approve_registration` | Organizer-only transition from `UNDER_REVIEW` to `APPROVED`, with a status event. Payment verification is evidence, not an automatic transition. |
| `reject_registration` | Organizer-only transition from `UNDER_REVIEW` to `REJECTED`, with an explanatory status event. |
| `submit_payment_attempt` | Create a manual proof attempt only for a non-zero-fee registration. |
| `review_payment_attempt` | Organizer-only verification or rejection of an individual payment attempt. |

For capacity and one-person-per-division checks, active registrations are those in `SUBMITTED`, `UNDER_REVIEW`, or `APPROVED`. A rejected registration no longer occupies capacity or blocks a claimed player from a new entry.

## Permissions and data exposure

| Actor | Allowed actions |
| --- | --- |
| Anonymous visitor | Read published tournament information and approved public teams/players/results once those read models exist. |
| Authenticated participant | Create a registration, view registrations submitted by their account, and submit payment evidence for those registrations. They cannot alter organizer decisions or view another account’s sensitive data. |
| Organizer | `is_staff=True` plus membership in the flat `Organizers` Django group. Uses Django Admin model permissions and the guarded review actions. |
| Superuser | Django’s built-in unrestricted administrator. |

Public serializers expose only approved, non-sensitive tournament data. They must never expose email addresses, payment files, payment references, review notes, or private eligibility material. Object ownership in DRF is based on `registration.submitted_by == request.user`; Django Guardian is not required for this v1 ownership rule.

## Implementation boundaries

Organize the backend into three focused apps:

- `accounts` for the custom user model and account-facing API;
- `tournaments` for `Game`, `Tournament`, and `Division`;
- `registrations` for registrations, members, payment attempts, status events, and domain services.

Views, serializers, and Django Admin actions call domain services. They do not independently reimplement a state transition or capacity check.

## Acceptance criteria

The implementation is not complete until automated tests show that:

1. a solo division accepts one member and rejects zero or more than one;
2. an exactly-five-player division is treated as a team division;
3. a non-playing manager can submit a team without becoming a player;
4. a claimed player cannot join two active registrations in the same division;
5. concurrent submissions cannot exceed division capacity;
6. a later profile gamer-tag or school change cannot change a historical public display;
7. a free registration needs no payment attempt;
8. a rejected proof is retained when a later proof is submitted;
9. payment verification alone cannot approve a registration;
10. participants cannot access another registration’s payment or review data; and
11. every organizer status transition produces a status event.
