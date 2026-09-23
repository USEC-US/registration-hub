## Local development

Copy `.env.example` to `.env`, then adjust database settings for your local environment.

Useful commands:

```powershell
uv run python manage.py migrate
uv run python manage.py bootstrap_organizers
uv run python manage.py sync_banks
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py import_institutions
uv run python manage.py check
uv run python manage.py test -v 2
uv run ruff check .
```

API documentation is mounted at `/api/docs/`. It is public while `DEBUG=True` and staff-only while `DEBUG=False`.

The bank catalogue and receiving-bank selector are available in Django Admin.
See [bank catalogue operations](../docs/payments/bank-catalogue.md) for initial
setup, manual refresh, and daily scheduling.

## Development seed data

After applying migrations, create or restore the local testing scenarios with:

```powershell
uv run python manage.py seed_dev_data
```

The command creates predictable credentials and normally requires `DEBUG=True`. For an intentional non-production test database configured with `DEBUG=False`, the explicit override is:

```powershell
uv run python manage.py seed_dev_data --allow-non-debug
```

Never use the override against a production database.

Test accounts:

| Role | Email | Password |
| --- | --- | --- |
| Player | `player@email.com` | `player@123` |
| Organizer | `organizer@email.com` | `organizer@123` |
| Admin | `admin@email.com` | `admin@123` |

The organizer is a least-privilege staff member in the `Organizers` group. The admin is a separate superuser so organizer permission boundaries remain testable.

## Organizer review and history

Run `uv run python manage.py bootstrap_organizers` after migrations, then add active
staff accounts to the **Organizers** group. The command grants registration view
and change, payment-attempt view and change, bank view and refresh, and the
relevant tournament and payment-setting permissions. It does not grant deletion
or account management. For narrower access, adjust the Organizers group's
permissions after bootstrapping; rerunning the command restores its default grants.

In **Registrations**, start review, then approve or reject with a reason. Paid
approval verifies a submitted image proof and requires both registration-change
and payment-attempt-change permissions. Bulk approval shows the effect on each
selected registration before confirmation; bulk rejection requires a reason.
Payment attempts remain read-only in admin. Check a registration's **History**
for actor and state changes, its status-event inline for reasons, and the
payment-attempt detail for reviewer, time, and note. Bank refresh entries appear
in each affected bank's **History**. Tournament, division, and payment-setting
edits use Django's built-in admin history. Never put credentials or private
contact details in review reasons.

Seeded tournament slugs:

- `dev-usec-current`: open, full, and upcoming registration scenarios;
- `dev-usec-archive`: closed and rejected historical scenarios;
- `dev-usec-draft`: unpublished admin-only scenario.

Rerunning the command resets the three documented accounts, the `dev-usec-*` tournament configuration, and registrations owned by `player@email.com` within those tournaments. It does not flush the database, remove registrations submitted by other accounts, or modify unrelated tournaments.
