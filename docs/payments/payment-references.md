# Payment references and future SePay integration

## Current behavior

Team registrations require a Team Name and a separate Team Tag. Tags accept 2–5 ASCII letters or digits, are stored uppercase, and may repeat across registrations. Solo entries have neither field. Existing records keep a blank tag until corrected by a future organizer workflow; the migration does not invent historical tags.

Paid registrations use a server-issued `PaymentIntent`. Its public reference is `USEC` followed by 10 cryptographically random uppercase letters/digits, excluding easily confused `0`, `1`, `I`, and `O`. A database uniqueness constraint and bounded collision retries protect uniqueness. The prefix is fixed for issued codes and is independent of team names, tags, player identities, and receiving bank accounts.

`POST /api/payment-references/` takes `tournament_game` and optionally an existing private `token`. It returns the reference, private token, amount, and currency. New issuance checks publication, registration dates, fees, and current capacity, and is throttled per IP. Issuing a reference does **not** reserve a roster or capacity slot. Responses are not cacheable. The browser keeps the token in session storage, scoped to the division, so refreshing the same tab resumes the code. If storage is unavailable, the current page keeps it in memory.

The private UUID token is a bearer claim handle, distinct from the public payment code. Submitting a registration attaches the intent atomically to exactly one registration, after checking the division and fee. A submitted code remains stable across proof uploads. A changed fee blocks submission with an organizer-contact message; it does not silently replace an already issued code. Lost tokens, payments followed by abandonment, closed/full divisions, and other payment exceptions require organizer reconciliation. Unattached intents remain available to organizers; codes are not recycled or automatically expired.

Guests still attach proof before submitting. Signed-in participants may submit first and upload proof later. Legacy paid registrations can obtain a code through the owner-only `POST /api/registrations/{id}/payment-reference/` endpoint. Historical `PaymentAttempt.reference` values are retained as private manual transaction notes. They are separate from the new generated reference, which is exposed as `payment_reference` in registration receipts/details. Historical transfers are not retroactively claimed to contain a newly generated code.

Generating a code or uploading proof never confirms payment. Organizer review remains authoritative. No SePay credentials, webhooks, gateway checkout, QR generation, or live bank connections are introduced by this change.

After applying the migrations, run `python manage.py bootstrap_organizers` to grant organizers read access to payment intents.

## SePay configuration and next integration

The agreed first integration is direct bank transfers with webhooks. Personal receiving accounts will depend on the organizer linked to SePay; there is no fixed receiving bank in this implementation. A later hosted gateway can reference the same payment intent.

For SePay payment-code extraction, configure:

- Prefix: `USEC`
- Suffix minimum and maximum: `10`
- Character type: letters and digits

SePay extracts this merchant code into webhook `code`. Its `referenceCode` is the **bank's** transaction reference; webhook `id` is the SePay transaction identifier. Store all three separately. References are identifiers, not authentication secrets.

Before enabling automatic verification, each intent must also snapshot the intended organizer/payment-account connection and receiving account/VA. Authenticate webhook delivery, match that destination and the expected amount/currency/incoming direction, and deduplicate deliveries using the provider connection/environment plus transaction ID. Persist receipt of money even when its intent has not yet been attached to a registration. Overpayments, underpayments, duplicate transfers, and unmatched codes need explicit reconciliation policies. Confirming payment must remain separate from approving tournament eligibility.

Build the full transfer description from the selected personal bank connection. Some connections require a virtual account, while VietinBank personal accounts require `SEVQR` in the description, and content-based VAs require `TKP` plus the VA code. The payment reference stays unchanged inside that description. Validate extraction in SePay test mode before configuring live accounts. The current UI asks for the code itself as the description for manual transfers; replace that guidance with the account-specific full description when SePay connections are introduced.

If deployed across multiple application workers, use shared cache storage for consistent API throttling. Design retention/cleanup for abandoned intents together with webhook reconciliation, so potentially paid references are not discarded.

## Official documentation reviewed

Reviewed 2026-09-12:

- [Payment-code structure](https://developer.sepay.vn/vi/sepay-webhooks/cau-hinh-ma-thanh-toan)
- [Webhook fields and duplicate deliveries](https://developer.sepay.vn/vi/sepay-webhooks/tich-hop-webhook)
- [VietQR parameters and bank-specific rules](https://developer.sepay.vn/vi/tien-ich-khac/tao-qr-code)
