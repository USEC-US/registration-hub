# Staged Registration and VietQR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Implementation was authorized on 2026-09-15 and is complete pending final whole-branch review. Deployment activation remains separate.**

**Goal:** Deliver automatically saved registration stages, browser-restored guest payment access, configurable unpaid reservation expiry, and locally generated VietQR using site-wide bank settings.

**Architecture:** Keep Django services authoritative for submission, availability, expiry, and payment review. Add narrow modules for reservation queries, private access, and VietQR; share payment UI between guests and account owners. Preserve historical records and use additive migrations.

**Tech Stack:** Django/DRF, PostgreSQL, Django Unfold admin, SvelteKit/Svelte 5, shadcn-svelte, Paraglide, Vitest, and Playwright. Add Python `qrcode` for local image encoding and a development-only independent QR decoder (`zxing-cpp`) during implementation; record resolved versions in `server/uv.lock`.

**Spec:** [Approved design](../specs/2026-09-15-staged-registration-vietqr-design.md). The user approved it in conversation on 2026-09-15.

## Global constraints

- Implementation is authorized on the isolated feature branch. No ordinary-database migration/seeding, production configuration, scheduler activation, merge, push, or real transfer is authorized.
- Stages: contact/team, roster, review/submit, then payment. Free entries finish after submission. No required account, email verification, or manually saved secret URL.
- Automatically save drafts for seven days without an edit. Drafts hold no slot. Browser-saved submitted access is separate from the draft and its expiry.
- Use a 256-bit random browser credential, hash it server-side, and send it only in a dedicated header. Never reuse payment-intent tokens or `USEC` references as credentials.
- Initial payment hold: 60 minutes by default; staff-configurable from 15 through 1440 minutes; capped at division registration close. Snapshot the duration and deadline. Never extend the deadline on reads or refreshes.
- Pending or verified proof protects the reservation. Rejected proof requires a reason and grants a replacement window from review time using the saved duration, even after registration close. Expired entries release capacity and player claims together while retaining records.
- Payment verification and eligibility approval remain separate. Approval of a new timed paid entry requires verified payment; existing historical approval behavior remains compatible.
- Bank settings apply site-wide. Holder names are manually entered and explicitly unverified. Defer account lookup, SePay, multiple receiving accounts, and tournament-specific receiving accounts.
- Snapshot bank destination, amount/currency, transfer content, and hold duration. Do not backfill unknown historical destinations or payment deadlines.
- QR: `QRIBFTTA`, `A000000727`, `VN`, currency `704`; exact positive whole-dong amounts. Never round or truncate. Include transfer content only when it fits the documented 25-character field; otherwise use bank-and-amount QR with explicit copy/paste instructions, including in the downloaded image.
- Preserve captain/manager, substitute, student-only, institution fallback, historical snapshots, proof-image sanitization, and public/private serializer boundaries.
- Lock division before registration before payment/access records. Backend time decides expiry. Correct availability must not depend on a scheduler having run.
- Retain existing legacy endpoints and initial multipart proof intake where valid. A client omitting the new credential must not gain an untimed new paid reservation.
- Follow English/Vietnamese locale routing and existing UI primitives. Do not add a new UI framework, production test hooks, or public payment-file access.

## Execution setup and file ownership

When implementation is requested, inspect `git status`, use CodeGraph before locating unfamiliar code, and establish a feature branch/workspace without overwriting unrelated changes. Read the spec and this plan once. Run the documented baseline checks and distinguish environment failures from application failures. No merge, push, production configuration, or real bank transfer is implied by this plan.

| Task | Owns | Depends on |
| --- | --- | --- |
| 1 | Receiving settings, QR encoding/rendering, additive schema | Existing payment intent and admin |
| 2 | Reservation queries, expiry, guarded review/upload | Task 1 fields/settings |
| 3 | Private access, idempotent intake, payment-session API | Tasks 1–2 services |
| 4 | Browser storage and typed API clients | Task 3 API contract |
| 5 | Staged form, payment page, account integration, translations | Tasks 1–4 |
| 6 | Real browser journeys, full regression checks, operational docs | Tasks 1–5 |

Execute in this order. Tasks 1–3 share `registrations/models.py`, services, serializers, and admin; do not edit those concurrently. Tasks 4–5 share API types and registration UI. A reviewer should check each task against the spec before the next task is marked complete. Checkmarks record completed task-level verification and review; final whole-branch review remains separately tracked.

## Shared contract

### Model additions

`PaymentSettings` in `server/registrations/models.py` is a singleton with fixed primary key `1`, `enabled=False`, `bank_name`, `bank_bin`, `account_number`, `account_holder`, and `payment_hold_minutes=60`. String destination fields default to empty while disabled. Apply a database check for singleton identity and duration range; validate a complete supported destination when enabled. Do not delete the singleton through admin.

Add nullable `Registration.payment_due_at` and `payment_hold_minutes_snapshot`; both remain null on existing rows. Add status `EXPIRED`. Add immutable bank snapshot fields to `PaymentIntent`: `bank_name_snapshot`, `bank_bin_snapshot`, `account_number_snapshot`, and `account_holder_snapshot`, initially blank for historical intents.

Add `RegistrationAccess` with `registration` (one-to-one), `credential_hash` (64-character SHA-256 hex, unique), `request_digest` (64-character SHA-256 hex), and creation time. The original actor is `Registration.submitted_by`; ordinary workflows never change it. Do not expose hashes in serializers/admin lists or allow manually assigning access to a historical guest record.

### API surfaces

The header is **`X-Registration-Access`**, containing exactly 64 lowercase hexadecimal characters representing 32 random bytes.

| Endpoint | Authorization and behavior |
| --- | --- |
| `POST /api/registrations/submit/` | Existing body/Turnstile; optional access header enables idempotent submission and saved guest access. Return existing receipt plus additive lifecycle fields; never echo the credential. New staged requests omit initial proof and payment-intent token. |
| `POST /api/registrations/resume/` | Access header required; locate a committed registration without knowing its ID. Return private session below. Unknown credential is 404, including before a request has committed. |
| `POST /api/registrations/{id}/payment-session/` | Either access credential for exactly this ID, or authenticated submitter JWT. Return the same private session. A supplied wrong credential does not fall through to another authority. |
| `POST /api/registrations/{id}/payment-proof/` | Same access rules; multipart `proof_file`, optional `reference`, and fresh `turnstile_token`. Derive amount/currency from the saved registration. Return the updated private session. |
| Existing `/payment-attempts/`, `/payment-reference/`, `/payment-instructions/` | Preserve existing owner-only authorization and response compatibility. Route mutations through the new lifecycle guards. |

Private session payload:

```typescript
type PaymentState = 'NOT_REQUIRED' | 'UNPAID' | 'PENDING' | 'VERIFIED' | 'REJECTED';
interface RegistrationPaymentSession {
  registration: RegistrationRead; // Existing receipt; status union gains EXPIRED.
  payment_state: PaymentState;
  payment_due_at: string | null;
  server_now: string;
  expired: boolean;
  can_upload_proof: boolean;
  can_retry_registration: boolean;
  replacement_note: string;
  saved_submission: RegistrationSubmissionPayload;
  institution_labels: Record<string, string>; // Original labels keyed by display_order.
  instructions: null | {
    bank_name: string;
    bank_bin: string;
    account_number: string;
    account_holder: string;
    amount: string;
    currency: string;
    transfer_content: string;
    transfer_content_limit: number;
    qr_payload: string | null;
    qr_png_data_url: string | null;
    qr_contains_transfer_content: boolean;
  };
}
```

`RegistrationRead` also gains `payment_state`, `payment_due_at`, and `expired` for account list/detail displays. These additions contain no private identities. `saved_submission` belongs only to the explicit private session and omits credentials, Turnstile, payment-intent tokens, and proof data. Retired or missing institution choices retain their original label and require explicit correction before a retry; do not silently rewrite submitted history.

For expired, rejected, pending, verified, and free entries, return no actionable QR and disable proof submission as appropriate. Historical instructions with no destination cannot produce a QR; explain organizer contact while preserving the permitted historical proof flow. All private success and error responses use `Cache-Control: private, no-store`.

Expose `payment_hold_minutes` and `payment_available` in public division responses for pre-submit guidance. The latter is false for a paid division whose current settings/amount/currency cannot support the new payment flow. Do not expose private credentials or roster data there.

## Task 1: Receiving settings, snapshots, and local QR

**Files**

- Modify `server/registrations/models.py`, `admin.py`, `payments.py`, `management/commands/bootstrap_organizers.py`.
- Create `server/registrations/vietqr.py`, `payment_settings.py`, and migration `0009_payment_settings_and_reservations.py` after the current `0008` migration; verify numbering at execution time.
- Modify `server/pyproject.toml`, `server/uv.lock`; use existing Pillow for annotated PNG output.
- Create `server/registrations/tests/test_vietqr.py`, `test_payment_settings.py`, `test_payment_reservation_migration.py`; extend `test_management_command.py` and `test_payment_reference.py`.

**Interfaces**

- `require_payment_settings(*, amount: Decimal, currency: str) -> PaymentSettings`: reject disabled/incomplete destination, unsupported currency, fractional/non-positive/oversized VND amount; no side effects.
- `build_vietqr(*, bank_bin: str, account_number: str, amount: Decimal, transfer_content: str) -> tuple[str, bool]`: exact payload and whether all transfer content is encoded.
- `render_vietqr_png(*, payload: str, copy_transfer_content: bool) -> bytes`: quiet-zone QR plus a readable copy-content instruction when required; no network access.
- `crc16(data: bytes) -> str`: uppercase, zero-padded four-character checksum.
- Extend `create_payment_intent(..., payment_settings=None)` to capture destination when explicitly supplied for a new registration. Default legacy calls do not invent historical destination snapshots.

- [x] **Write failing encoder and settings tests.** Start with an independently known checksum and a complete payload vector; keep these tests independent of Django database setup:

```python
from decimal import Decimal
from django.test import SimpleTestCase
from registrations.vietqr import build_vietqr, crc16

class VietQrTests(SimpleTestCase):
    def test_crc_known_vector(self):
        self.assertEqual(crc16(b"123456789"), "29B1")

    def test_exact_transfer_vector(self):
        payload, includes_content = build_vietqr(
            bank_bin="970415", account_number="0011001932418",
            amount=Decimal("120000"), transfer_content="ung ho lu lut",
        )
        self.assertTrue(includes_content)
        self.assertEqual(payload,
            "00020101021238570010A0000007270127000697041501130011001932418"
            "0208QRIBFTTA530370454061200005802VN62170813ung ho lu lut6304C15C")
```

The transfer vector is from the generator reference linked in the spec; verify its provenance at execution. Do not copy the inconsistent printed dynamic account example from the bundled PDF as a supposedly valid vector.

- [x] **Run the failing tests** from `server/`: `TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test registrations.tests.test_vietqr --keepdb --noinput`. Confirm missing encoder behavior rather than a fixture/environment error.
- [x] **Implement strict payload construction and local rendering.** During execution, use `uv add qrcode` and `uv add --dev zxing-cpp` from `server/`; inspect the resolved official package documentation and commit the lockfile. Assemble root tags `00=01`, `01=12`, nested `38`, `53=704`, `54`, `58=VN`, optional `62/08`, and terminal `6304` before checksum. Use Decimal, preserve leading zeroes, reject non-ASCII unsupported account syntax, enforce account length 1–19 and BIN of six ASCII digits. Enforce all two-digit lengths. The composition rule is:

```python
merchant = tlv("00", "A000000727") + tlv(
    "01", tlv("00", bank_bin) + tlv("01", account_number)
) + tlv("02", "QRIBFTTA")
```

`tlv(tag, value)` is a private helper defined in this task that validates ASCII payload values and length at most 99. QR transfer content must already be the exact saved normalized string. If it exceeds 25 characters or cannot be represented exactly in the supported encoding, omit it and return `False`; do not transliterate again. Render the QR using `qrcode`, annotate the long-content fallback in readable ASCII Vietnamese and English using Pillow's available font, and retain a proper quiet zone.

- [x] **Add settings/admin and additive migrations.** Include the shared model additions except `RegistrationAccess` (Task 3). Add `paymentsettings` add/change/view permissions to `bootstrap_organizers`, while preventing multiple settings rows and deletion. Test ordinary staff, organizer without the model permission, fully authorized organizer, and superuser. Do not change a real receiving account or seed one into normal environments.
- [x] **Verify edge cases and migration preservation.** Test 25/26-character text, six-digit BIN syntax, 19/20-character accounts, fractional amounts, amounts above 13 digits, leading zeroes, disabled settings, snapshot stability after a settings change, PNG independently decoded with `zxing-cpp`, and annotated long-content fallback. MigrationExecutor tests must create pre-migration registrations/intents and prove deadlines remain null and destination fields blank afterward. Run focused tests and migration checks; commit the reviewed settings/QR/schema files.

## Task 2: Reservation expiry and payment review

**Files**

- Create `server/registrations/reservations.py` and `management/commands/expire_unpaid_registrations.py`.
- Modify `server/registrations/services.py`, `payments.py`, `serializers.py`, `admin.py`; `server/tournaments/views.py`, `serializers.py`.
- Create `server/registrations/tests/test_reservations.py`, `test_reservation_concurrency.py`; extend `test_services.py`, `test_admin_actions.py`, `test_api.py`, `server/tournaments/tests/test_api.py`.

**Interfaces**

- `active_registrations(*, now: datetime) -> QuerySet[Registration]`: active review status excluding effectively overdue unpaid entries.
- `payment_state(registration: Registration) -> str`: free first, then any verified proof, then any pending proof, then rejected proof, otherwise unpaid.
- `is_expired(registration: Registration, *, now: datetime) -> bool`: explicit `EXPIRED` or overdue active paid entry without pending/verified proof.
- `expire_due_registrations(*, division_id: int | None = None) -> int`: idempotent materialization and events, with server time checked under locks.
- Extend `submit_payment_attempt(..., registration_access=None)` to authorize an owner or a validated `RegistrationAccess` object; never accept a boolean “guest authorized” from request data.

- [x] **Write deterministic deadline tests** using `RegistrationOwnershipApiTests.setUp`, which supplies published division, owner, and historical registration fixtures. Example method for a new TestCase that reuses that setup:

```python
def test_overdue_unpaid_entry_stops_holding_capacity_without_cron(self):
    now = timezone.now()
    self.registration.payment_due_at = now
    self.registration.payment_hold_minutes_snapshot = 60
    self.registration.save()
    self.assertFalse(active_registrations(now=now).filter(
        pk=self.registration.pk
    ).exists())
    self.assertTrue(Registration.objects.filter(pk=self.registration.pk).exists())
```

Add the complementary case with a real pending `PaymentAttempt` that continues holding capacity past the deadline. Tests mutate persisted records and call real queries/services; do not mock `active_registrations`.

- [x] **Run the failing reservation tests**, then implement the shared predicate. Use `Exists` to avoid multiplying registrations when several attempts exist:

```python
protected = PaymentAttempt.objects.filter(
    registration_id=OuterRef("pk"), status__in=("PENDING", "VERIFIED")
)
active = Registration.objects.alias(
    protected_payment=Exists(protected)
).filter(status__in=Registration.active_statuses()).exclude(
    fee_amount_snapshot__gt=0, payment_due_at__lte=now,
    protected_payment=False,
)
```

Public availability counts must use these effective active IDs, including serializer fallback counts. The same rule applies to old payment-reference issuance, duplicate claims, and submit capacity checks. Null deadlines preserve historical behavior.

- [x] **Implement expiry and the management command.** Lock each division, then affected registration rows, reevaluate state/time, set `EXPIRED`, and append one event. Use the command's `--division ID` option for scoped operation and testing. A second run reports zero newly expired entries. Any lazy cleanup performed inside a transaction that subsequently fails may roll back; effective reads must still release its capacity immediately.
- [x] **Update all related mutations to the same lock order.** Cover submit, initial proof, later proof, organizer transitions, payment review, and intent creation/attachment. New paid entries receive deadline snapshots even when the caller omits a saved-access credential. Validate/sanitize proof, then check deadline under locks before persisting it. Ensure stored files are removed if persistence or commit fails. For timed entries reject duplicate pending uploads, verified/expired/rejected entry uploads, and unpaid eligibility approval. Preserve appropriate legacy behavior for historical null-deadline records.
- [x] **Implement replacement-proof review and verify races.** The rejected-proof admin action needs a reason form; it may not silently send a blank note. Update the saved deadline to review time plus the original duration only after a pending attempt transitions to rejected and no pending/verified attempt remains. Registration rejection releases capacity immediately. Use PostgreSQL TransactionTestCase, independent connections, and barriers to test last-slot contention, duplicate claims, simultaneous credential-free submissions, proof versus expiry, review versus cleanup, and repeated cleanup. Run focused Django and tournament tests; commit the reviewed lifecycle change.

## Task 3: Idempotent saved access and private payment API

**Files**

- Create `server/registrations/access.py`, `payment_sessions.py`, `private_views.py`.
- Modify `models.py`, `services.py`, `views.py`, `serializers.py`, `urls.py`, `permissions.py`, and `server/config/settings.py`.
- Add migration `0010_registration_access.py` after Task 1's migration.
- Create `server/registrations/tests/test_registration_access.py`, `test_payment_sessions.py`; extend `test_guest_submission.py`, `test_payment_reference.py`, `test_images.py`.

**Interfaces**

- `hash_credential(raw: str) -> str`: validate exact header format and return SHA-256 hex; malformed headers fail explicitly.
- `submission_digest(payload: dict) -> str`: canonical JSON hash, excluding Turnstile and credentials; deterministic handling of omitted defaults and input ordering.
- `resolve_registration_access(raw: str, *, registration_id: int | None = None) -> RegistrationAccess`: scoped lookup or not-found, never a global guest listing.
- `build_payment_session(registration: Registration) -> dict`: shared private payload using server time, effective expiry, saved destination and existing review state.
- Extend `submit_registration(..., access_credential: str | None = None, request_digest: str | None = None)` and perform access creation in the same transaction as registration/roster/intent/events.

- [x] **Write a failing end-to-end API contract test.** Reuse the fixture setup and `payload()` from `GuestSubmissionTests`, enable a test-only `PaymentSettings`, and submit without initial proof:

```python
def test_guest_can_resume_committed_submission_without_id(self):
    secret = "ab" * 32
    response = self.client.post(
        "/api/registrations/submit/", self.payload(), format="json",
        HTTP_X_REGISTRATION_ACCESS=secret,
    )
    self.assertEqual(response.status_code, 201, response.data)
    resumed = self.client.post(
        "/api/registrations/resume/", {}, format="json",
        HTTP_X_REGISTRATION_ACCESS=secret,
    )
    self.assertEqual(resumed.status_code, 200, resumed.data)
    self.assertEqual(resumed.data["registration"]["id"], response.data["id"])
    self.assertEqual(resumed.data["payment_state"], "UNPAID")
    self.assertNotIn(secret, str(resumed.data))
    self.assertIn("no-store", resumed["Cache-Control"])
```

- [x] **Run the failing API tests and implement canonical replay.** Permit a credential to identify only one original actor/division/payload. Exclude `turnstile_token`, normalize known optional defaults (`team_tag`, optional contacts/manager name, member `roster_role` and Student ID), preserve member array order, and serialize with sorted object keys. If a compatibility request combines saved access and initial multipart proof, include the original file-byte digest and manual reference in the request digest and rewind the file before validation; changing proof must not be treated as an identical request. Compare a committed request before mutable business validation so changed dates, capacity, institution review state, or roster settings do not make a lost success unrecoverable. Validate the original request and Turnstile before creating anything. A retry needs a fresh Turnstile token; resume is a read and does not. Return 201 for the first creation and 200 for an identical replay, with the same ID and unchanged deadline. Return 409 for changed actor/division/payload. A unique constraint plus a recoverable inner transaction/savepoint must settle concurrent same-credential requests, including requests aimed at different divisions.
- [x] **Implement the private routes and owner path.** Match the shared API table. Use an explicit credential-based permission adapter; do not mistake `AnonymousUser.pk == None` for ownership of a guest registration. Preserve access to saved entries after registration closes or a tournament is unpublished, but block new payment actions for unpublished events. Bad or mismatched credentials get non-enumerating errors. Add the custom header to `CORS_ALLOW_HEADERS` using `corsheaders.defaults.default_headers`. Apply throttles to private read/resume and proof routes; preserve Turnstile on proof submission. Keep proof downloads JWT/admin-only.
- [x] **Integrate new submission and legacy intake.** New staged intake creates the intent only at submission, snapshots enabled settings, accepts paid guests without proof, and returns the additive receipt. Missing bank configuration, invalid VND fee, or transfer text over the configured manual limit fails without consuming capacity, creating custom institutions, or losing draft data. Existing submitted records get no backfilled destination/deadline. Pre-existing unattached quote tokens keep their fee/template snapshots and explicit legacy-session recovery rules; do not silently attach today's bank details to an old quote. Legacy requests with initial proof keep their image and amount checks. Missing the saved-access header must not bypass current new-registration payment deadlines.
- [x] **Verify permissions, retries, and historical compatibility.** Cover wrong/absent/malformed credentials, known IDs without authority, guest receipt privacy, signed-in actor mismatch, key-order/default normalization, changed data, concurrent same-key requests, immutable deadlines on replay, no credentials stored in plain text, legacy intents, unknown tokens, lost response recovery, terminal payment states, rejected proof notes, and private cache headers on errors. Extend existing owner-only tests rather than loosening their expectations. Run focused tests, migration checks, and OpenAPI validation; commit the reviewed access/API change.

## Task 4: Browser draft/access storage and typed clients

**Files**

- Create `web/src/lib/registrations/browser-storage.ts`, `browser-storage.test.ts`, `submission.ts`, `submission.test.ts`.
- Modify `web/src/lib/api/types.ts`, `registrations.ts`, `registrations.test.ts`; reuse `requestJson` header support from `client.ts`.

**Interfaces**

```typescript
type DraftStage = 'details' | 'roster' | 'review';
interface RegistrationDraft {
  version: 1;
  gameId: number;
  updatedAt: number;
  stage: DraftStage;
  fields: RegistrationSubmissionPayload;
  institutionLabels: Record<string, string>;
}
type SavedRegistrationAccess = {
  version: 1;
  gameId: number;
  credential: string;
} & (
  | {
      attemptState: 'prepared' | 'uncertain';
      registrationId: null;
      submittedPayload: RegistrationSubmissionPayload;
    }
  | {
      attemptState: 'submitted';
      registrationId: number;
    }
);
```

Store an allowlisted draft under `usec-registration-draft:v1:{gameId}` and each saved attempt separately under `usec-registration-access:v1:{credential}`. Enumerate matching keys for the current division instead of rewriting a shared array that can lose another tab's entry. Once the ID is known, replace the pending record with the submitted variant and remove its local personal payload; the authorized server snapshot is the recovery source.

- `readDraft(storage: Storage, gameId: number, now: number): RegistrationDraft | null`.
- `writeDraft(storage: Storage, draft: RegistrationDraft): boolean`; `clearDraft(storage: Storage, gameId: number): boolean`.
- `createCredential(): string` using `crypto.getRandomValues(new Uint8Array(32))` and two-character hex per byte.
- `saveAccess(storage: Storage, entry: SavedRegistrationAccess): boolean`; `listAccess(storage: Storage, gameId: number): SavedRegistrationAccess[]`; `forgetAccess(storage: Storage, credential: string): boolean`.
- `submitSavedRegistration(accessToken, payload, turnstileToken, credential): Promise<RegistrationRead>`; `resumeRegistration(credential): Promise<RegistrationPaymentSession>`; `getPaymentSession(id, {accessToken?, credential?})`; `uploadPaymentProof(id, formData, {accessToken?, credential?})`.

- [x] **Write failing storage tests with a real in-memory Storage implementation** inside the test module. It implements `getItem`, `setItem`, `removeItem`, `clear`, `key`, and `length` over a Map. Test expired/malformed drafts without depending on browser globals. Example after inserting a valid draft fixture with `updatedAt: 1000`:

```typescript
expect(readDraft(storage, 9, 1000 + 7 * 24 * 60 * 60 * 1000)).toBeNull();
expect(listAccess(storage, 9)).toHaveLength(1); // Access was saved separately.
```

The fixture contains actual contact, player identity, institution choice, and stage values. Assert those values survive a round-trip before checking expiry. Add explicit failure cases for forbidden proof/challenge/JWT fields and storage operations throwing DOMException.

- [x] **Run `pnpm exec vitest run --project server src/lib/registrations/browser-storage.test.ts` from `web/`**, then implement allowlisted parsing/storage and credential generation. Unknown schema versions, wrong division IDs, invalid stages, invalid payload shapes, and malformed saved-access entries must not reach form state. Catch reads/writes/removals individually. Access to localStorage itself can throw; callers need an in-memory fallback for the current page and a visible persistence warning.
- [x] **Implement submission recovery and typed clients.** Save a credential plus exact attempted fields before sending the request. Mark a transport failure uncertain; do not discard its key or create a fresh one. On return, resume first. A 404 alone cannot prove the original request is no longer in flight: re-submit the same payload/key with a fresh challenge, letting server idempotency settle it. After a definite validation rejection, permit editing; after confirmed success, save the ID and clear the draft. Never switch a signed-in uncertain attempt silently to a guest after token expiry. Present the account-session recovery path. API client headers are:

```typescript
const headers = credential ? { 'X-Registration-Access': credential } : undefined;
return requestJson<RegistrationPaymentSession>('/registrations/resume/', {
  method: 'POST', headers, body: {}
});
```

- [x] **Test observable recovery behavior.** Cover 201 and replay 200, uncertain submit then successful resume, unknown-credential retry using the same key, changed payload requiring resolution, auth expiry, quota failure, two entries in one division, clearing a draft without clearing submitted access, and forgetting only one entry. API tests assert header/body routing and response/error handling with complete response fixtures; storage tests use real parsing/storage logic.
- [x] **Run focused Vitest and Svelte checks**, then commit the reviewed browser storage and API-client files. No component changes belong in this task.

## Task 5: Registration stages and the shared payment page

**Files**

- Modify `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte` and `+page.ts`.
- Create `web/src/lib/components/registrations/RegistrationDetailsStep.svelte`, `RegistrationReviewStep.svelte`, `RegistrationSteps.svelte`, `SavedRegistrationChoices.svelte`, and `RegistrationPaymentPanel.svelte`.
- Create `web/src/routes/registrations/[id]/payment/+page.svelte`; private data loads only after browser auth/access resolution, not in public SSR data.
- Reuse/modify `RosterEditor.svelte`, `PaymentProofField.svelte`, `PaymentAttemptForm.svelte`, `TransferContentField.svelte`, and `StatusTimeline.svelte` only where the shared flow needs it.
- Modify account registration list/detail pages; `web/messages/en.json`, `vi.json`; `registration-pages.svelte.spec.ts`, `public-registration.e2e.ts` and relevant component tests. Create `registration-stages.svelte.spec.ts` and `registration-payment.svelte.spec.ts`.

**Interfaces**

`RegistrationSteps` receives current stage and allowed completed stages and emits navigation requests. `RegistrationDetailsStep` binds team/contact/role fields. `RegistrationReviewStep` receives read-only fields, original institution labels, fee, and hold duration. `RegistrationPaymentPanel` receives a private session, credential or owner token, and an updated-session callback. It uses the Task 4 client functions; it never constructs a bank destination from public current settings.

- [x] **Write failing browser-component tests for the stage flow.** Render the real page with a complete division fixture. Enter contact fields, Continue to roster, fill real roster controls, go Back, and assert values persist. Attempt invalid Continue and assert the active stage and focused error. Restore a saved draft after remount, accept Continue, and verify the saved stage/values. Test URL `?step=details|roster|review`, browser Back, and invalid/direct future-stage URLs. Example assertions after progressing through the fixture:

```typescript
await expect.element(page.getByRole('heading', { name: 'Review registration' })).toBeVisible();
await expect.element(page.getByRole('button', { name: 'Submit registration', exact: true })).toBeVisible();
await expect.element(page.getByLabel('Payment proof', { exact: true })).not.toBeInTheDocument();
```

Use the actual localized message values selected during implementation; these are the intended English roles, not a reason to hardcode component text.

- [x] **Run the failing component tests and extract the staged form.** Keep only one active form stage in the DOM; do not leave hidden required inputs blocking native validation. Details validation includes role, manager name, team tag/name, and contacts. Roster validation includes required mains, substitutes, captain, names/birth dates, student-only IDs, and institution choices; Django repeats authoritative validation. Review shows the submitted identity and original institution labels. A seven-day draft restores without deleting extra members after roster configuration changes. Do not let `RosterEditor` auto-initialization overwrite restored rows.
- [x] **Wire autosave and submission transitions.** Debounce saves by 300 ms, flush on visibility/pagehide and route departure, and avoid overwriting a stored draft before the user chooses Continue/Discard. Read a fresh draft on remount; do not share module-global personal form state between SSR users. Show saved-device status/clear action and storage-unavailable feedback. Use Task 4's pending credential before final submit; only submission starts the hold. Paid success navigates to the new payment page; free success shows a saved confirmation. Division revisits list saved submitted entries even when the division is full or closed.
- [x] **Implement payment, recovery, and retry UI.** Load private data with the saved credential or owner token. Show the exact deadline and a countdown anchored to `server_now`; re-fetch on visibility and at expiry without using the browser clock as authority. Render bank/holder/amount/full transfer text and local PNG, with copy controls and an annotated image download. When QR omits text, prominently require pasting the full transfer text. Never show a QR or upload button for expired/rejected entries or after pending/verified proof. Upload needs a fresh Turnstile token and existing image selection validation; don't persist files. Pending status offers refresh, verified status distinguishes eligibility review, rejected proof shows the staff note and replacement deadline. Expired/rejected records can create a fresh editable draft from the private saved fields if registration remains available. Keep the old record and require a new final submission. Clearing device access never sends a cancellation request.
- [x] **Verify shared account behavior and accessibility.** Account list/detail show the same lifecycle and link to the shared payment page. Historical entries without bank snapshots retain their documented proof path and organizer-contact copy. Wrong/missing saved access shows a recovery explanation without exposing a record. Test keyboard focus, stage heading announcements, validation summaries, mobile layout, EN/VI paths, clipboard failures, disabled storage, lost responses, long-text QR fallback, free entries, and switching among saved manager submissions. Run focused browser Vitest, `pnpm check`, and changed-file lint/format checks; commit reviewed UI/messages/tests.

## Task 6: Real journeys, deployment instructions, and completion evidence

**Files**

- Modify `server/e2e/serve.py`, `web/e2e/django/registration.spec.ts`, and `web/playwright.django.config.ts` only if test startup needs adjustment.
- Extend `server/registrations/dev_seed.py` and `tests/test_seed_dev_data_command.py` so development fixtures remain valid without overwriting an operator's configured bank. Keep fake receiving settings confined to disposable test data or explicit command-owned development fixtures.
- Update `docs/testing/registration-journey.md`, `docs/payments/payment-references.md`, `docs/deployment/payment-images.md`, `docs/deployment/security-rate-limits.md`, and `docs/TODO.md` after verification. Add `docs/deployment/payment-reservations.md`.

- [x] **Write and run failing real-browser journeys before adapting fixtures.** Seed settings with clearly identified test-only values in the disposable database. Add journeys for a guest paid entry returning in a new tab, signed-in entry, free captain, manager with substitute captain, lost submission response, pending proof, staff rejection/replacement, staff verification followed by eligibility approval, and expired-entry retry. Existing real API routes remain unmocked. To simulate a lost response, forward the real submission to Django and then drop the browser response; verify one persisted registration by resuming with the saved credential. Keep application state and resulting API calls real.
- [x] **Exercise expiry without waiting 60 minutes.** Add a disposable expired fixture in `server/e2e/serve.py` through real submission followed by test-fixture-only clock/deadline setup. Provide its synthetic credential through a fixture file or controlled test bootstrap, never a production API. Browser tests assert the old saved entry remains visible and payment is disabled; backend boundary/race tests already establish the actual expiry calculation. Never rely on changing Playwright's browser clock to advance Django time.
- [x] **Run the full verification commands**, preserving environment files and separating baseline/tooling diagnostics from failures:

```sh
# Working directory: server/
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py test --keepdb --noinput
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py makemigrations --check --dry-run
TURNSTILE_SECRET_KEY=test-only-key .venv/bin/python manage.py check
.venv/bin/ruff check .

# Working directory: web/
pnpm check
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec vitest run
PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test
PLAYWRIGHT_BROWSERS_PATH=/tmp/hcmusec-playwright pnpm exec playwright test --config playwright.django.config.ts
PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA pnpm build
```

Run ESLint/Prettier against the changed frontend files and `git diff --check`. If a required browser or dependency is absent, install it as an implementation prerequisite rather than labelling the product broken. The real Django harness needs ports 8015/4175, PostgreSQL credentials with test-database creation permission, and Chromium. Confirm disposable databases and media are removed afterward. Executed results and environment diagnostics are recorded in the Task 6 report.

- [x] **Document activation and recovery.** Production/staging activation requires additive migrations, `bootstrap_organizers`, authorized bank configuration, and an expiry scheduler every minute. Document `manage.py expire_unpaid_registrations` and a scheduler invoking the deployed virtualenv from the deployed `server/` directory with its normal environment. A missed schedule may delay persisted events, but effective availability still releases slots. Include missing/disabled settings, rotated destination snapshots, rejected proof, late transfers, lost browser access, and rollback: do not drop new access/snapshot fields or revert to older capacity-counting code while timed entries exist. Closing new paid intake is safer than silently reverting reservation semantics. Do not actually activate a scheduler or configure a real bank during implementation unless separately authorized.
- [ ] **Perform final review and update evidence.** Review the combined diff for privacy, expiry and upload races, legacy compatibility, credential/idempotency behavior, and UI preservation. Resolve substantive findings and re-run only affected checks. Record exact commands/results and any remaining environment limits. Mark the two new registration TODO items complete only when their implemented acceptance cases pass. Keep account-holder verification/SePay deferred. Record that a real bank-app scan and deployment scheduler checks remain operational acceptance steps unless actually performed; never make a real transfer just to test QR.

## Plan self-review and handoff

| Spec area | Implementation and verification |
| --- | --- |
| Stages, automatic drafts, no lost form values | Tasks 4–5; storage and component tests, Task 6 real journeys |
| Saved guest access, no email/secret-link workflow | Tasks 3–5; scoped API, lost-response and browser-return tests |
| Configurable hold, expiry, replacement window | Tasks 1–2; deterministic PostgreSQL boundary/race tests |
| Shared effective capacity and player claims | Task 2; public-query, submission, cleanup, and concurrency tests |
| Site-wide bank settings and historical snapshots | Tasks 1 and 3; permissions/migrations/legacy tests |
| Local QR, exact values, long-text fallback | Tasks 1 and 5; vector/decoder and UI/download tests |
| Private proof and separate eligibility approval | Tasks 2–3 and 5; permissions/review/real-browser coverage |
| Deployment and documented validation | Task 6; migration, scheduler and operational acceptance notes |

Tasks 1–5 passed scoped implementation reviews. Task 6 acceptance implementation is complete pending scoped review and final whole-branch review. The implementation report records verification and environment limitations. No merge, push, production bank configuration, expiry scheduler activation, or real transfer has been performed.
