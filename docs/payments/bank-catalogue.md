# Bank catalogue and receiving-bank selection

Django Admin → **Registrations → Banks** lists locally stored bank names, codes,
six-digit BINs, active status, and last successful refresh time. Search accepts the
full name, short name, bank code, BIN, or SWIFT code. The catalogue is read-only;
authorized organizers can use **Refresh bank catalogue** to update it.

In **Payment settings**, use the searchable **Bank** selector, then enter the
receiving account number and account-holder name. Saving derives the bank name
and BIN from the local catalogue. Account numbers keep their leading zeroes.
The catalogue does not verify account ownership or account-holder names.

## Initial setup

Run from `server/` against the intended database:

```sh
uv run python manage.py migrate
uv run python manage.py bootstrap_organizers
uv run python manage.py sync_banks
```

Migration `0011_bank` adds only the catalogue table. Existing receiving settings
and issued payment instructions are not rewritten. `bootstrap_organizers` grants
organizers catalogue viewing and refresh permissions, without manual creation,
editing, or deletion of bank rows.

## Refreshing

The source is CASSO's public [VietQR.io bank-list API](https://api.vietqr.io/v2/banks),
not a direct SBV registry feed. Its [documentation](https://vietqr.io/danh-sach-api/api-danh-sach-ma-ngan-hang/)
recommends daily cache refreshes. Schedule the following command once per day with
the deployment's scheduler, using the same environment as Django:

```sh
uv run python manage.py sync_banks
```

No recurring job is installed automatically. Staff can also refresh on demand
from the Banks page. That action requires a CSRF-protected POST and organizer
membership plus both `view_bank` and `change_bank` permissions (or a superuser).

For a preview or an offline import of a saved API response:

```sh
uv run python manage.py sync_banks --dry-run
uv run python manage.py sync_banks --file /path/to/banks.json --dry-run
uv run python manage.py sync_banks --file /path/to/banks.json
```

The complete response is validated before an atomic update keyed by BIN. Empty,
malformed, duplicate-BIN, and failed responses leave the last saved list intact.
Network requests have a 15-second timeout and a 1 MiB response limit. BINs are
stored as text. Banks absent from a successful response become inactive and can
be reactivated by a later refresh; they are never deleted.

## Payment continuity

Admin reads and payment requests use local data and do not call the catalogue
API. Refreshing the catalogue never changes payment settings or historical
payment snapshots. Selecting a bank and saving payment settings changes the
destination for future payment instructions only.

An existing configured BIN remains selectable even if the catalogue is empty or
the bank becomes inactive. New selections use active catalogue entries. The API's
`transferSupported` flag describes the bank app's scanning support; it is not used
to reject receiving-bank choices. `lookupSupported` is also informational and does
not perform account validation. QR generation continues locally.
