# Development seed data design

**Status:** approved design  
**Date:** 2026-07-20

## Purpose

Provide deterministic, representative local data for manually exercising the Django Admin, REST API, and SvelteKit participant experience. Developers should be able to populate or restore the scenarios with one explicit Django management command without flushing unrelated local records.

The seed data is development support, not production bootstrap data and not a replacement for focused fixtures inside automated unit tests.

## Goals

- Provide documented participant, organizer, and superuser logins.
- Exercise all public tournament availability states.
- Exercise every registration review state and representative payment states.
- Keep registration windows useful by calculating dates relative to the time the command runs.
- Make reruns deterministic while preserving unrelated local data.
- Create domain records through existing registration, payment, and review services where practical.
- Verify the management command itself with automated Django tests.

## Non-goals

- Generate a large performance or pagination dataset.
- Add reusable Factory Boy factories or a new test-data dependency.
- Create payment-proof media files.
- Load production reference data.
- Run automatically during migration, deployment, or server startup.
- Replace the existing `bootstrap_organizers` command.

## Command interface

Add a Django management command under the registrations application:

```powershell
uv run python manage.py seed_dev_data
```

The command is explicit and development-only. Because it creates predictable credentials, it refuses to run while `DEBUG=False` unless the developer supplies:

```powershell
uv run python manage.py seed_dev_data --allow-non-debug
```

The override is intentionally conspicuous and must be documented as unsafe for production databases.

On success, the command prints:

- each test account and password;
- seeded tournament names and slugs;
- a short map of the registration and payment scenarios;
- a reminder that rerunning restores command-owned records.

## Transaction and time handling

The command captures `timezone.now()` once and uses that value for all relative dates. This avoids inconsistent availability states if a run crosses a time boundary.

The complete seed operation runs inside one `transaction.atomic()` block. A validation, permission, bootstrap, or database failure raises `CommandError` and rolls back the full operation.

The command invokes the existing `bootstrap_organizers` management command before assigning the organizer account to the group. Domain services are used for registration submission, payment submission and review, and organizer status transitions.

For a historical registration whose final registration window is closed, the command may create the scenario while its window is temporarily valid, apply the normal domain operations, and then set its final historical dates. Scenario timestamps are adjusted relative to the captured seed time so the UI presents a coherent history.

## Seed ownership and rerun behavior

The following identifiers are command-owned:

- the documented account email addresses;
- tournament slugs prefixed with `dev-usec-`;
- registrations owned by `player@email.com` inside those development tournaments;
- payment attempts and status events attached to those registrations.

Games use their normal catalog slugs because they represent reusable real games. Existing matching games are reconciled by slug rather than duplicated.

On every run, the command:

1. creates or updates the known accounts and resets their passwords and role flags;
2. creates or updates the known games, tournaments, and tournament-game configuration;
3. removes registrations owned by `player@email.com` within the seeded development tournaments;
4. recreates the canonical registration, status-event, and payment-attempt scenarios;
5. leaves records outside the documented account emails and development tournament slugs untouched.

This means manual changes made to command-owned scenarios are intentionally restored by rerunning the command. It does not flush the database and does not delete registrations submitted by other users, even when those registrations belong to a seeded tournament.

## Accounts

| Role | Email | Password | Profile and permissions |
| --- | --- | --- | --- |
| Participant | `player@email.com` | `player@123` | Normal active user with a gamer tag and school suitable for form prefilling. |
| Organizer | `organizer@email.com` | `organizer@123` | Active staff account in the least-privilege `Organizers` group; not a superuser. |
| Administrator | `admin@email.com` | `admin@123` | Active Django staff superuser; separate from the organizer to preserve permission-boundary testing. |

The organizer and administrator remain separate because organizer workflows must be testable without superuser privileges masking permission errors.

## Tournament and registration scenarios

### Current published tournament

Create one currently active published tournament with slug `dev-usec-current`.

| Game | Public availability | Format | Fee and capacity | Player registration |
| --- | --- | --- | --- | --- |
| Valorant | `open` | Five-player team | Paid with available capacity | `SUBMITTED` with one pending reference-only payment attempt. |
| Chess | `open` | Solo | Free with unlimited capacity | `APPROVED` with no payment attempts. |
| Counter-Strike 2 | `full` | Five-player team | Paid with capacity one | `UNDER_REVIEW` with one verified reference-only payment attempt. |
| League of Legends | `not_open` | Five-player team | Paid | No registration. |

Team rosters use deterministic free-text player snapshots. The sole Chess member is the captain. Every team registration has exactly one captain and contiguous display order.

### Published historical tournament

Create one published past tournament with slug `dev-usec-archive`. Its Rocket League registration window is closed.

The participant owns a three-player paid Rocket League registration in `REJECTED` status. It contains:

- the initial submission event;
- an organizer transition to `UNDER_REVIEW`;
- an organizer transition to `REJECTED` with a non-empty reason;
- one rejected reference-only payment attempt;
- one pending replacement payment attempt.

This scenario exercises closed public registration, rejection history, retained rejected payment evidence, and a corrected payment attempt.

### Unpublished draft tournament

Create one unpublished tournament with slug `dev-usec-draft` and at least one configured tournament game.

It must be visible to authorized staff in Django Admin but absent from public API responses. Participant submission through the domain service must remain invalid because the tournament is unpublished.

## Coverage matrix

The seeded public tournament games cover:

- `open`;
- `full`;
- `not_open`;
- `closed`.

The participant's registration list covers:

- `SUBMITTED`;
- `UNDER_REVIEW`;
- `APPROVED`;
- `REJECTED`.

Payment histories cover:

- no payment required;
- `PENDING`;
- `VERIFIED`;
- `REJECTED` followed by a replacement attempt.

The tournament set also covers public visibility versus an unpublished admin-only draft.

## Error handling

- Unsafe execution without `DEBUG=True` or `--allow-non-debug` raises `CommandError` before data is changed.
- Missing organizer permissions propagate from `bootstrap_organizers` as a command failure.
- Domain validation and permission failures abort and roll back the transaction.
- Predictable credentials are never created automatically by migrations or startup hooks.
- The command generates no media files. Payment attempts use deterministic transfer-reference strings.
- Output must clearly state which identifiers are command-owned and may be restored on rerun.

## Automated tests

Add focused management-command tests using Django's test framework and `call_command`.

The tests verify that:

1. the command refuses to run with `DEBUG=False` unless the explicit override is supplied;
2. the participant, organizer, and administrator have the documented passwords and exact role flags;
3. the organizer belongs to the bootstrapped `Organizers` group and receives its least-privilege permissions;
4. published, unpublished, open, full, upcoming, and closed data is created correctly;
5. the participant has one canonical registration in each review state;
6. payment scenarios include pending, verified, and rejected records without proof files;
7. status-event histories follow the allowed transition sequence;
8. a second command run leaves canonical counts unchanged;
9. rerunning restores modified command-owned profile, role, catalog, password, registration, and payment data;
10. unrelated users, tournaments, and registrations survive reruns unchanged;
11. a forced failure during seeding rolls back all changes from that run;
12. public tournament API responses hide the draft tournament and report the expected availability states;
13. successful command output includes the credentials and scenario summary.

Tests should assert meaningful relationships and states rather than relying on hard-coded database primary keys.

## Documentation

Update `server/README.md` with:

- the normal `seed_dev_data` invocation;
- the non-debug safety override and warning;
- the three credentials;
- the development tournament slugs;
- a concise explanation of which records are restored during reruns.

## Verification

Run from `server/`:

```powershell
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run python manage.py test -v 2
uv run ruff check .
```

The change should require no model migration and no frontend source change.

## Acceptance criteria

The work is complete when a developer can migrate an empty local database, run `seed_dev_data`, sign in with every documented account, see the expected public and private scenarios, rerun the command without duplicate canonical records, and retain unrelated locally created data. The full backend verification suite must pass.
