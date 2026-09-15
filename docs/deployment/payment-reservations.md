# Payment reservations: activation and recovery

Deploy the additive migrations with the new backend before serving the staged frontend. From the deployed `server/` directory, using its normal deployment environment and virtualenv:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py bootstrap_organizers
.venv/bin/python manage.py check
```

In Django admin, an authorized operator configures the site-wide **Payment settings** singleton: bank name, six-digit BIN, account number, manually entered holder name, enabled flag, and hold duration. Holder names are unverified; account lookup and SePay remain deferred. Verify the intended destination independently before enabling intake. Disabled/missing settings block new paid submissions; free submissions remain available. Do not use development fixture destinations for real payments.

The default hold is 60 minutes, configurable from 15 to 1440 minutes. Each paid submission snapshots its duration, bank destination, amount/currency, transfer content, and deadline. Initial deadlines are capped at division registration close. Refreshing does not extend them. Updating bank settings affects future submissions only; coordinate reconciliation for transfers to historical destinations.

Schedule expiry every minute. For example, a cron entry owned by the application service user may invoke:

```cron
* * * * * cd /srv/registration/server && /srv/registration/server/.venv/bin/python manage.py expire_unpaid_registrations >> /var/log/registration-expiry.log 2>&1
```

Replace these example paths with the deployed paths and provide the same environment/secret loading as the backend service. Confirm the command succeeds under the scheduler's actual user and environment, and monitor failures. A manual run uses `.venv/bin/python manage.py expire_unpaid_registrations` from that same directory. No scheduler is installed by this repository change.

A missed schedule can delay persisted EXPIRED events. Effective availability and duplicate-player claims still release overdue unpaid entries using backend time; they do not depend on cron. Pending or verified proof protects a reservation. Rejected proof requires a staff reason and starts a replacement window using the saved duration from review time, even after registration closes. Expired records remain visible but cannot accept payment proof; retry creates a separate editable draft when intake is available. Verification of payment and eligibility approval are separate staff decisions.

## Recovery

- **Rejected proof:** explain the correction in the staff reason. The participant refreshes the saved payment page and uploads replacement evidence within the displayed deadline.
- **Late transfer:** retain the old registration and evidence; ask the organizer to reconcile it before creating another payment. Never treat an expired QR or reference as authority to reserve a new place.
- **Lost response:** use “Recover pending submission” on the original browser. The saved credential resolves the committed registration without duplicating it.
- **Lost browser access:** sign in as the submitting account when applicable. Guests must return on the original browser or contact organizers; an internal `USEC` reference is not an access credential. Clearing device access does not cancel an entry.
- **Disabled settings:** restore authorized configuration for new paid intake. Existing entries use their saved destination, including after bank rotation. Historical records lacking a destination direct participants to organizers; do not invent a destination snapshot.
- **Rollback:** retain all new access, deadline, and snapshot fields. Do not deploy older capacity-counting code while timed registrations exist or drop these additive fields. Closing new paid intake is safer than reverting reservation semantics. Keep compatible read/review/reconciliation access for saved entries.

Before launch, perform a bank-app scan against the authorized destination and check the scheduler in the deployed environment. Inspect the exact account, whole-dong amount, and transfer content (copy/paste the full text when the QR cannot contain it). A real transfer is not necessary for this implementation's tests and is not authorized by them.
