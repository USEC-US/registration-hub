# Identity refactor completion design

## Purpose

Complete the existing account-identity refactor so every backend and frontend consumer agrees with the current account contract. This is a compatibility repair, not the deferred institution-catalogue feature.

## Current contract

- An account is an authenticated actor, not a player profile.
- `User` requires `email`, `first_name`, and `last_name` when created through the user manager.
- `school` remains the current account field until the separately planned institution-catalogue migration replaces it.
- `student_id` remains private staff-reference data and is not added to public account API responses.
- `gamer_tag` is not an account field. Gamer tags and roster institutions remain registration snapshots.

## Scope

### Backend

- Update all test-user factories and direct `create_user` calls to provide valid first and last names.
- Update development seed creation to stop supplying the deleted `gamer_tag` field and to create valid named users.
- Update account API tests for the current registration and profile payloads: name fields plus `school`, without `gamer_tag`.
- Preserve the existing user model, migrations, service rules, API paths, and Django Admin behavior.

### Frontend

- Remove `gamer_tag` and `school` prefill from the tournament-registration flow.
- Remove the profile fetch that existed solely to obtain those roster defaults; an access token remains sufficient to submit a registration.
- Initialize every roster member with empty snapshot text while preserving captain and display-order initialization.
- Restore the `field_gamer_tag` message because it labels a registration-roster input, not an account property.
- Update frontend fixtures, route tests, and mocked account responses to match `CurrentUser` (`id`, `email`, `first_name`, `last_name`, `school`).

## Explicit exclusions

- Do not implement the institution catalogue, search endpoint, import command, combobox, or account migration described in the July 22 design.
- Do not change RichText/Paraglide typings.
- Do not change redirect-localization behavior or its separate navigation-test mismatch.
- Do not redesign roster snapshots, payment, tournament, or Django Admin workflows.

## Data flow

```text
Access token
  -> registration page
  -> empty roster snapshot inputs
  -> registration submit API
  -> immutable member snapshots on Registration
```

The authenticated user remains the `Registration.submitted_by` value set by the server. Roster members do not inherit account-profile values.

## Verification

- `uv run python manage.py makemigrations --check --dry-run`
- `uv run ruff check .`
- `uv run python manage.py test -v 1`
- Identity-specific frontend checks and tests pass after their fixtures and route dependencies are updated.
- Any remaining RichText/Paraglide type errors and navigation-localization test failures are reported as excluded baseline issues.
