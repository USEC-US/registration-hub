# Section 4: Organizer registration operations plan

Finish organizer permissions and audit coverage in the existing Django admin.
Organizers retain access across all tournaments, with each action gated by its
Django permission. CSV export is deferred until club operations has a concrete
need.

Paid registration approval may verify pending payment proof in the same action.
This must be clearly labelled and require both registration-change and
payment-change permissions. Standalone payment review remains available.

Source: [TODO Section 4](../../TODO.md#4-organizer-registration-operations) and
[General Delivery Plan](../../GENERAL-PLAN.md).

## Action items

- [ ] **Verify permissions across every entry point.** Review list/detail pages,
  inlines, bulk actions, proof downloads, and service calls. Require active
  organizer membership and the relevant Django permission, while preserving
  Django's superuser access. Check the permission grants in
  `server/registrations/management/commands/bootstrap_organizers.py`; preserve
  restrictions on deletion, account management, and editing submitted snapshots.

- [ ] **Make combined approval explicit.** In
  [admin.py](../../../server/registrations/admin.py), show **“Verify payment and
  approve”** when approval will verify pending proof. Require both
  registration-change and payment-change permissions. Free entries and entries
  with verified payment use **“Approve registration.”** Bulk confirmation must
  explain which operations will occur.

- [ ] **Preserve atomic decisions.** Keep verification and approval together in
  the existing transaction in
  [services.py](../../../server/registrations/services.py). Missing permissions,
  missing proof, expiry, or a conflicting decision must leave no partial
  approval. Bulk actions should report each success and failure accurately.

- [ ] **Complete audit coverage using existing records.** Retain registration
  status events and payment reviewer/time/note fields. Add Django admin history
  entries for custom review actions and bank refreshes; verify existing history
  for tournament, division, and payment-setting changes. Record the actor,
  affected record, action, previous/resulting state, and reason where required.
  Combined approval must identify both decisions.

- [ ] **Protect audit integrity and privacy.** Write successful decision history
  in the same transaction as the decision. Failed or repeated requests must not
  create false success records. Keep history read-only for organizers, preserve
  earlier payment attempts, require meaningful rejection reasons—including bulk
  rejection—and exclude credentials, proof contents, and unnecessary contact
  data from logs.

- [ ] **Verify focused acceptance cases.** Cover view-only organizers, missing
  either permission, unrelated staff, disabled accounts, and superusers; then
  paid/free approval, standalone payment review, mixed bulk selections, expired
  entries, concurrent decisions, rollback, and audit visibility. Run the
  registration/tournament Django tests on PostgreSQL, backend lint, and migration
  checks, followed by an admin smoke check. Extend the existing service, admin,
  API, permission, and management-command tests for the affected paths.

- [ ] **Update the roadmap and operating notes.** Amend
  [TODO.md](../../TODO.md) and [GENERAL-PLAN.md](../../GENERAL-PLAN.md) to describe
  combined approval accurately, record CSV's deferral, and document permission
  setup and audit lookup.

## Completion condition

Authorized organizers can review registrations with clear payment consequences,
and every consequential action has protected, attributable history.

Next: [Section 5 competition formats plan](2026-09-23-competition-formats.md).
