# Account identity and institution catalogue design

## Purpose

Align accounts with their limited role in the registration system. An account identifies an authenticated actor: a separate registration manager, a team captain, or a solo player. It is not a complete participant profile and it does not own game-specific identity.

This design replaces the account's free-text `school` field with a shared institution catalogue, preserves the private staff-auditing use of `student_id`, and completes the existing first-name/last-name migration.

## Goals

- Require first name, last name, email, password, and institution when a new account is registered.
- Let an account holder select an institution from the supplied catalogue or enter a missing institution without being blocked.
- Store each institution once, so staff review a custom institution once rather than once per account.
- Keep `student_id` private and usable only for club-staff auditing.
- Make catalogue and review state usable by a future frontend administration panel without building that panel now.

## Non-goals

- Collecting phone numbers, dates of birth, or other participant data on accounts.
- Validating player eligibility or institution membership automatically.
- Changing the tournament registration form's roster fields or snapshot schema.
- Tracking a persistent cross-game gamer tag.
- Building a frontend staff administration panel.

## Data model

### Institution

`Institution` is a PostgreSQL-backed shared catalogue. Its application fields map directly to the supplied `university.json` schema:

| API field | Source field | Notes |
| --- | --- | --- |
| `value` | `value` | Catalogue provider identifier; blank for custom records. |
| `label` | `label` | Required display name. |
| `code` | `code` | Blank for custom records. |
| `shortName` | `shortName` | Blank for custom records. |
| `eng` | `eng` | Blank for custom records. |
| `type` | `type` | Blank for custom records. |
| `location` | `location` | Blank for custom records. |

Database field names may follow Django's snake-case conventions, but the account and search APIs serialize the object using the source schema above.

Every record also has internal-only metadata:

- `source`: `CATALOGUE` or `CUSTOM`;
- `review_status`: `VERIFIED`, `PENDING`, or `REJECTED`;
- `normalized_label`: a case-folded, whitespace-normalized lookup value.

Catalogue imports create verified records and retain their source `value`. A custom entry has only a `label`, is pending review, and has blank catalogue fields. Before creating a custom record, the service first finds a verified catalogue entry with the same normalized label, then an existing custom entry with that label. A conditional uniqueness constraint on custom normalized labels makes concurrent custom submissions converge on one shared record.

### User

`User.school` is replaced with `User.institution`, a foreign key to `Institution`. The user-facing account contract is:

- required: `email`, `password` at registration, `first_name`, `last_name`, and `institution`;
- read-only to the account holder: `id` and `email`;
- editable by the account holder: `first_name`, `last_name`, and `institution`;
- private: `student_id`.

`student_id` must be blank for non-staff accounts. Staff accounts require it and club staff manage it in Django Admin. It is excluded from all public and self-service account serializers.

Existing non-empty `school` values migrate to shared label-only pending institutions. Empty legacy school values are preserved as no institution at the database layer; new registration and completed profile submissions require an institution.

## Catalogue loading and staff administration

An idempotent management command imports `server/university.json` into `Institution`. It creates and updates catalogue records by source `value` without overwriting custom entries or staff review decisions. The dataset remains a source import, not a runtime application dependency or browser asset.

Django Admin is the staff interface in this slice. It exposes institution source and review status for filtering and review, and exposes `student_id` only in staff-account workflows. A future frontend admin panel can use the same explicit models and review state; no current behavior depends on Django templates.

## API and user flow

`GET /api/institutions/?q=<text>` provides a small, ranked set of catalogue matches. It searches display label, code, short name, English name, and location. The client never loads the complete dataset.

Account registration and profile updates accept exactly one institution choice:

- a catalogue institution identifier, which the server resolves to its canonical record; or
- a non-empty custom label, which the server resolves or creates as a shared pending record.

Account responses return the selected institution in the source-shaped schema above, but do not expose staff-only review details or `student_id`.

The registration and profile pages use an accessible, GitHub-style combobox: typing searches the catalogue, keyboard or pointer selection chooses a result, and a no-match value can be submitted as free text. A pending custom entry does not prevent sign-in, profile use, or tournament registration. Staff may later verify it or contact the account holder if it is invalid.

## Registration boundary

Game names and institution information entered for tournament roster members remain registration snapshots. The account no longer provides `gamer_tag` or a school default. This slice only removes account-profile assumptions from consumers; a later registration-form design will decide roster field collection, validation, and any institution reuse.

## Migration and compatibility

Schema changes create the institution table and link users to it. A deterministic data migration converts old `school` text into pending records before removing that column. The catalogue import runs separately from schema migration so migration history does not depend on a mutable project file.

The account frontend and API types replace `school` with `institution`. Related tests and fixtures must create users with required names. Existing registration snapshots remain unchanged.

## Verification

Backend coverage verifies:

- idempotent catalogue import and updates by source `value`;
- normalized custom-label reuse and catalogue-label resolution;
- registration/profile validation and canonical institution resolution;
- migration of old school text;
- absence of `student_id` from account APIs and its staff-only validation.

Frontend coverage verifies catalogue search, keyboard selection, free-text fallback, and profile edits. The project health report must continue to distinguish these checks from pre-existing RichText and locale-test failures outside this slice.
