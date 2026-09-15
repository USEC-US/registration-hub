# Payment proof images

Payment proof uploads require a still JPEG, PNG, or WebP image, at most 10 MiB and
20 megapixels. References are optional. The backend decodes and re-encodes
accepted images, removes metadata and trailing bytes, and generates filenames.
Existing payment records remain readable. Development seeds now include images
clearly marked as development samples.

Proof downloads at `/media/payment-proofs/...` must reach Django. The view
requires the submitter's JWT or an authorized organizer's JWT/admin session.
Responses are attachments with `private, no-store`; the public development
media handler excludes this directory, including normalized traversal paths.

When configuring production media, never expose `payment-proofs/` through a
public bucket, CDN, or generic static alias. Route that prefix to Django before
any public `/media/` rule. For example, with an upstream named `django`:

```nginx
location ^~ /media/payment-proofs/ {
    proxy_pass http://django;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Set the upload request body limit above the file limit to allow multipart
overhead, for example `client_max_body_size 11m`. The application enforces the
10 MiB file limit; the proxy bounds total request size. Keep this rule on both
the API host and any host proxying the Django admin.

Both guests and signed-in participants submit registration before uploading proof on the saved payment page. The private `/api/registrations/{id}/payment-proof/` route accepts the entry-scoped access header or submitter JWT and a fresh Turnstile challenge. Legacy multipart initial proof remains compatible. Pending/verified proof protects the reservation; expiry and replacement guards are enforced on the backend. See [reservation operations](payment-reservations.md). Guest saved access does not make proof downloads public or grant a generic media credential.

The development seed uses fictional destination snapshots only inside its command-owned fixtures and restores existing bank configuration atomically, including disabled state and hold duration. It does not leave fictional receiving settings enabled.
