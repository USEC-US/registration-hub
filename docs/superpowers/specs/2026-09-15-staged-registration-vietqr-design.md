# Staged registration, saved guest access, and VietQR payments

Date: 2026-09-15

Status: Proposed design for final review. The staged flow, automatic browser
saving, submission before payment, configurable 60-minute payment hold, and QR
fallback for long transfer text are agreed.

## Purpose and scope

Complete the two new registration tasks in `docs/TODO.md`: divide registration
into manageable stages and generate VietQR from site-wide receiving-bank
settings. Support payment after submission without requiring an account, email,
or a manually saved secret link.

The participant flow is:

1. Contact and team details.
2. Main players and optional substitutes.
3. Review and submit.
4. Payment instructions, proof upload, and staff verification.

Free entries finish after submission. Captain/manager rules, student eligibility
collection, institution fallback, and private historical snapshots remain in
force. Payment verification never automatically approves eligibility.

This design supersedes the guest-proof-before-submission rule for new staged
submissions in the August registration design and payment-reference notes.
Existing registrations, proof records, and issued instructions remain historical
records; migration must not invent receiving accounts or payment deadlines.

## Alternatives considered

- Splitting the existing form while retaining proof before submission is smaller,
  but does not satisfy the agreed saved-unpaid-registration flow.
- Email delivery or a link the participant must save can support another device,
  but introduces a new recovery dependency the user explicitly declined.
- Browser-saved private access supports returning on the same browser without
  extra participant actions. This is the selected approach. Clearing browser
  storage or switching devices still requires organizer assistance.

## Stages and draft saving

Use the existing registration route with a numbered progress indicator and
Back/Continue controls. The active stage is reflected in the URL so browser Back
works. Validate a stage before proceeding and allow returning to completed
stages. Final server errors return the participant to the relevant stage without
discarding values. Focus the stage heading or error summary after navigation.

Automatically save a versioned draft to localStorage, scoped to the division.
Store contact/team fields, roster identity and institution selections, and the
current stage. Save after a short debounce and flush pending changes when leaving
the page. Drafts expire after seven days without an edit and reserve no capacity.
Returning offers Continue or Discard rather than silently overwriting a new form.

Show “Progress is saved on this device” and a Clear saved progress action. Handle
unavailable storage, malformed JSON, stale versions, and quota failures without
breaking registration; explain when only the current page can retain progress.
Never persist payment-proof images, Turnstile tokens, passwords, or access JWTs
inside the draft. Payment proof is selected on the submitted payment page.

Restore the saved field values against current division rules. Preserve surplus
or now-invalid player entries for correction rather than deleting them when
roster limits change. Revalidate institution choices and student-only policy on
submission. Display the fee and reservation duration before the final submit
action. Only the server creates the payment deadline.

## Saved submission and guest access

Add a dedicated private registration-access credential, separate from the
existing payment-intent token and public-facing payment reference. Its scope is
one submitted registration: private receipt, saved details for explicit retry,
payment instructions/status, and proof submission. It does not allow registration
editing, eligibility decisions, account access, or listing other registrations.

Generate a cryptographically random 256-bit credential in the browser and save it
before the submission request. Persist only its hash on the server. Treat the
credential as an idempotency key as well: a response lost after server commit can
be recovered using the saved credential without creating a second entry. Bind
replays to the original actor, division, and canonical submitted payload; reject
attempts to reuse a credential for different data. Refreshing a Turnstile token
must not change the canonical payload. Existing legacy submission clients remain
supported without acquiring new guest access to historical registrations.

Keep a browser index of saved submitted entries, including registration/division
IDs and the credential. Save a pending-submission index entry before sending the
request, independently of the draft's expiry. A dedicated private resume endpoint
can locate the committed registration by credential when its ID was lost with the
response. Resolve an uncertain submission before allowing a new credential for
the same in-progress attempt. After successful submission, remove the unfinished draft
and show the payment page. Return visits to the division offer Continue payment
or View registration. Preserve earlier submitted entries when a manager submits
another team. Signed-in users also have their existing account history.

Credentials travel in a dedicated request header, never a URL query, path,
analytics field, or normal serializer. Configure the API CORS header allowlist.
Registration IDs and `USEC` references alone grant no access. Private endpoints
and responses use `private, no-store`; the generic account list/detail permissions
stay owner-only. Add throttling to the credential-based resume/read/upload
endpoints using the existing DRF throttle infrastructure, and document the same
edge/origin deployment boundary as the other sensitive endpoints. A narrowly
scoped private serializer may return contact and
roster identity fields for the authorized saved entry; public/ordinary receipt
serializers must not gain those fields.

Guest access need not include proof downloads. Existing JWT/admin download
permissions remain intact. “Forget this registration on this device” removes
the saved access locally without cancelling the server registration. Organizer
access remains available if browser storage is lost. Do not add email recovery,
cross-device discovery, or a manually copied secret-link requirement.

## Reservation and payment lifecycle

Keep registration review status and payment status separate. Add `EXPIRED` to
registration status for released unpaid entries and retain status-event history.
Expose payment states `NOT_REQUIRED`, `UNPAID`, `PENDING`, `VERIFIED`, and
`REJECTED` as derived states from the fee and payment attempts. Expose reservation
expiry independently so an expired unpaid entry is unambiguous.

Store a nullable `payment_due_at` and the configured hold-duration snapshot on
new paid registrations. The initial deadline is the earlier of submission time
plus the configured duration and the division registration-closing time. The
default is 60 minutes. Staff configure the duration in site payment settings;
allow whole minutes from 15 through 1440. Settings edits never extend or shorten
already issued deadlines. Free entries and migrated historical entries have no
new automatic payment deadline.

An active paid entry with a deadline at or before server time and neither pending
nor verified proof expires. Its capacity and normalized player claims are
released together. Expiry preserves the registration, roster, contacts, payment
intent, and status events. An approved entry must not be permitted to bypass
payment expiry: for new timed paid entries, staff approval requires verified
payment. Payment verification itself does not change review status.

Valid proof accepted before the deadline changes payment to Pending verification
and protects the reservation while staff review. Invalid uploads do not extend
the deadline. Do not allow additional proof while an attempt is pending or after
payment is verified. All file validation and rollback-cleanup guarantees remain.

If staff reject proof, require an explanation. When no pending/verified attempt
remains, grant one replacement window using the entry's hold-duration snapshot
starting at review time. This replacement window may extend beyond registration
closing so staff delay does not remove the chance to correct proof. Staff can
instead reject the registration to release it immediately. A replacement upload
requires the same validation and review; opening the page never renews a hold.

After expiry, normal proof submission and QR payment actions are unavailable.
Show the expired deadline, organizer contact for already-made transfers, and
Register again using these details. Retrying creates a fresh editable draft and
new submission credential; it does not reactivate the old entry or transfer its
payment evidence. Capacity, player claims, current settings, and registration
dates are checked again. Late bank transfers require staff reconciliation and
never automatically reclaim a slot.

## Expiry correctness and concurrency

Define one backend rule for effective active reservations and use it in public
capacity counts, duplicate-player checks, submission, proof upload, and organizer
transitions. Overdue unpaid entries must stop blocking capacity even if a
scheduled cleanup has not run.

Use a consistent lock order: division, registration, then payment records. Recheck
server time and effective state under those locks before accepting a new entry,
proof, review, or expiry. An upload racing expiry either becomes pending in time
or receives an expired response; it must not revive a released reservation.

Materialize expirations and append exactly one status event in transactional
services. Provide an idempotent management command suitable for running every
minute. Reads calculate effective expiry and availability without depending on
cron; mutations settle expired entries under the division lock. Document the
scheduler command and cover both scheduled and lazy expiry paths.

## Site-wide receiving-bank settings

Add a singleton payment-settings model in the registration/payment domain and
expose it through Django Admin. Store enabled state, bank display name, six-digit
BIN, receiving account number, manually entered account-holder name, and default
payment-hold minutes. Restrict changes to authorized organizer staff with the
specific model permission or superusers; log changes through admin history.

Validate required fields and supported QR syntax before enabling. Account numbers
remain strings with leading zeroes preserved. A configured name is staff-provided,
not bank-verified. Account ownership validation, account-holder lookup, SePay,
multiple receiving accounts, and tournament-specific account routing are deferred.

Snapshot bank name/BIN, account number, holder name, amount, currency, transfer
content, and hold duration with each new payment intent/registration. Generate QR
and manual instructions only from these snapshots. A later bank-settings change
must not silently redirect an existing participant's payment.

Do not start a new timed paid registration when payment settings are missing or
disabled. Preserve the draft and explain that organizers must configure payment.
Free registrations remain available. Old intents with no destination snapshot
remain readable and can follow their existing proof-upload flow; never fabricate
historical instructions from today's bank settings. Keep existing unattached
quote tokens subject to their existing explicit legacy-session handling rather
than silently migrating them into new instructions after a possible transfer.

## Local VietQR generation

Build a small backend payload utility from the repository's NAPAS QR switching
specification v1.5.2. Render the resulting payload using a maintained QR encoding
library locally. No QR-service credentials or runtime external generation API
are required. Serve/display QR only for the authorized active payment page.

Use account transfer service `QRIBFTTA`, NAPAS AID `A000000727`, the snapshotted
BIN/account, country `VN`, VND currency code `704`, an exact positive whole-dong
amount, and CRC-16/CCITT-FALSE. Validate every nested tag/length/value boundary,
account length, and amount length. Do not round, truncate, or substitute values.
Non-VND historical payment records retain their existing manual flow; the new
VietQR payment configuration supports VND registrations only and must explain an
unsupported currency before accepting a timed submission.

The bundled specification limits the purpose-of-transaction field (62/08) to 25
characters. Existing transfer text can be longer. The agreed fallback is:

- When the exact normalized saved transfer text fits, include it in the QR.
- Otherwise generate bank-and-amount QR without transfer text, prominently tell
  participants to paste the complete displayed transfer content in their bank
  app, and provide Copy transfer content. The QR image/download carries the same
  instruction so it does not appear to contain all payment details.
- Never shorten saved text, replace it with the internal reference, or change
  historical templates just to fit the QR.

Test against published payload/CRC examples, structurally decode generated
payloads, and independently decode a rendered QR. The bundled dynamic example
contains inconsistent printed lengths, so any corrected fixture must document
the correction and must not be presented as a verbatim valid vector. Automated
checks establish encoding correctness; actual bank-app compatibility requires a
scan-only manual check with a configured receiving account before deployment.

Sources: bundled `docs/vietqr-format/QR_Format_T&C_v1.5.2_EN_102022.pdf`, especially
sections 5.2.3.2, 5.2.14, 5.2.15, and 6.3; and the
[referenced generator's input limitations](https://github.com/subiz/vietqr/blob/master/README.md#l%C6%B0u-%C3%BD-v%E1%BB%81-d%E1%BB%AF-li%E1%BB%87u-%C4%91%E1%BA%A7u-v%C3%A0o).

## Implementation boundaries

Extend `registrations/models.py`, payment and domain services, serializers,
permissions, views, URLs, and organizer admin. Keep expiry/access/QR concerns in
focused modules rather than expanding one large service or page indefinitely.
Update tournament availability queries to use effective active reservations.

Compose stages from the existing form controls, roster editor, and shadcn-svelte
primitives. Extract browser draft/access storage into tested modules. Add a
dedicated payment page and shared instructions/proof/status component for guests
and account owners. Preserve English/Vietnamese routing and messages, keyboard
navigation, reduced motion, and mobile layouts.

Apply additive migrations with safe historical defaults. Update explicit
organizer group permissions and disposable browser-test fixtures. Do not mark the
new TODO items complete until the implemented flow and required checks pass.

## Acceptance and verification

1. Guest and signed-in captain, manager, and solo entries complete all stages;
   validation errors preserve values and focus the correct stage. Refresh, tab
   close, malformed/expired drafts, and blocked storage have defined behavior.
2. Paid guests submit without proof, automatically recover their payment page,
   and recover a committed submission after a lost response. Wrong credentials,
   guessed IDs, actor changes, and changed-payload replays cannot expose or alter
   another registration. Existing public/private serializer boundaries hold.
3. A new paid entry reserves capacity for the snapshotted deadline. Boundary-time
   tests, concurrent submissions, proof/expiry races, lazy counts, cron runs, and
   duplicate claim release agree. Historical and free entries do not gain expiry.
4. Pending proof survives staff delay; rejected proof gets the documented
   replacement window; verified payment remains separate from eligibility.
   Expired entries preserve details and can only retry through a new valid entry.
5. Settings permissions, missing configuration, changed bank/fee snapshots,
   leading-zero accounts, QR payload lengths/CRC, long-content fallback, image
   decoding, proof privacy, and file cleanup have meaningful automated coverage.

Run Django/PostgreSQL tests including concurrency and migrations, Svelte checks,
Vitest, relevant lint/format checks, production build, and the real Django
Playwright journeys. Record actual results in the registration verification notes
and document the required expiry schedule. Do not report bank-app scan success or
production scheduler deployment without performing those checks.
