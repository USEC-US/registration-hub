# Payment references and transfer content

## Current manual-payment flow

Team registrations require a Team Name and a separate Team Tag: 2–5 ASCII letters/digits, stored uppercase, with repeats allowed. Solo entrants use their in-game name for payment instructions.

**Transfer content** is the text participants copy into their bank transfer description. Staff configure `Transfer content template` and `Transfer content limit` on the tournament in Django admin. The default template is:

```text
{participant} thanh toan le phi {tournament_name}
```

`{participant}` becomes the team tag or solo player's in-game name; `{tournament_name}` becomes the tournament name. Staff can write a fixed event name or fixed text instead, for example:

```text
{participant} thanh toan le phi cho giai dau USEC Championship XV
```

Accents, including Vietnamese đ/Đ, are removed and whitespace is collapsed in the displayed/copied text and server snapshot. Original names remain unchanged. Literal braces can be escaped as `{{` and `}}`; unsupported placeholders, format specifications, and conversions are rejected. The character limit defaults to 100 and staff can set it from 1 to 150 for their receiving bank. The UI shows the count; both UI and server reject content over the limit instead of truncating it. A shorter staff template may be necessary for long event or player names.

**Payment reference** is an independent tracking identifier: `USEC` plus 10 cryptographically random uppercase letters/digits, excluding confusing `0`, `1`, `I`, and `O`. Database uniqueness and bounded collision retries protect it. It never determines or gets appended to transfer content. Participants see it only after successful registration submission, on the guest confirmation or signed-in registration detail. A displayed reference does not mean payment has been verified. Staff can search either reference or transfer content in the payment-intent admin.

Guests still attach proof before submitting. Signed-in participants may upload it afterward. Uploads remain pending until staff verify them; payment verification is separate from tournament eligibility approval. Gateway checkout is not displayed: no usable gateway connection has been configured in this implementation.

## Payment sessions and snapshots

The existing `POST /api/payment-references/` URL is retained for compatibility, but it now returns only a private `token`, the partially resolved `transfer_content_template`, `transfer_content_limit`, amount, and currency. It does **not** return the internal reference. The browser substitutes the participant for its live preview. The server independently renders the final content from the submitted roster/tag and saves it on the intent when registration succeeds.

Issuance checks tournament publication, registration dates, fees, and capacity, but does not reserve a roster or capacity slot. Responses are not cacheable and issuance is throttled. The browser keeps the private UUID claim token in session storage, scoped to the division; refresh resumes the same quote and template snapshot. A later tournament edit does not rewrite instructions already issued. The token attaches an intent atomically to one registration. Fee changes block submission and require organizer assistance; rejected content does not consume the intent. Codes are not expired or recycled.

Signed-in owners get saved instructions through `POST /api/registrations/{id}/payment-instructions/`. The older owner-only `/payment-reference/` endpoint still returns the reference for an already submitted registration. Neither endpoint exposes another participant's records.

Existing intents predate transfer snapshots. Their new content/template fields remain blank: the migration does not invent what participants were previously told. An old unattached session cannot be silently resumed with new instructions; the participant is directed to organizers. Existing submitted records with blank content can still upload proof, with a message to contact staff if they need transfer instructions. Historical `PaymentAttempt.reference` values remain private manual transaction notes. Legacy registrations without any intent can receive one through the owner endpoints.

Apply the new migrations before using the updated UI. No new organizer permissions are required.

## Next payment-page task

Move payment to a separate page after registration submission, covering manual bank transfers, proof upload, and staff confirmation. The user chose to keep that move out of this pass. Design private return access for guests and a clear unpaid/pending/verified lifecycle before replacing the current guest-proof-before-submission rule. Future submission editing is also separate work. Show a gateway option only when its connection is configured and usable.

## Future SePay integration

Direct bank transfers with webhooks remain the first intended integration. Personal receiving accounts depend on the organizer connected to SePay; no receiving bank is fixed here. A hosted gateway can follow later.

SePay's `content` is the bank transfer text. Its nullable `code` is extracted from that text using the merchant's configured payment-code pattern; `referenceCode` is the bank's transaction reference and `id` is the SePay transaction identifier. Store those separately from this application's internal reference. The old recommendation to extract `USEC` references from transfer descriptions is superseded by this design.

Staff text and repeatable team tags are not unique payment identifiers. A webhook must not automatically approve a registration just because its text matches. Before automated verification, define account/destination snapshots and unambiguous reconciliation (or an account-specific payment identifier), verify incoming amount/currency/destination, authenticate delivery, and deduplicate by provider connection/environment plus transaction ID. Ambiguous, unmatched, duplicate, underpaid, and overpaid transfers require explicit handling. Bank-specific VA or description requirements belong to the configured bank connection, not to the internal tracking reference.

Official documentation (webhook contract rechecked 2026-09-14):

- [Webhook fields, extracted codes, and duplicate deliveries](https://developer.sepay.vn/vi/sepay-webhooks/tich-hop-webhook)
- [Payment-code structure](https://developer.sepay.vn/vi/sepay-webhooks/cau-hinh-ma-thanh-toan)
- [VietQR parameters and bank-specific rules](https://developer.sepay.vn/vi/tien-ich-khac/tao-qr-code)
