# Registration Journey Completion Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for implementation and review. This plan updates the existing August implementation plan to match the current repository and the approved initial guest payment upload.

**Goal:** Complete section 3 with guest and signed-in registration, institution snapshots, duplicate protection, and verified Django browser journeys.

**Architecture:** Keep the existing registration service and organizer admin. Make submission public but retain protected account reads and proof downloads. Submit initial proof atomically with registration, using existing image sanitization.

**Tech Stack:** Django/DRF, PostgreSQL, Svelte 5, shadcn-svelte, Vitest and Playwright.

**Spec:** `docs/superpowers/specs/2026-08-01-guest-first-tournament-registration-design.md`

## Global Constraints

- No permanent account role; captains occupy roster slot 1 and managers stay outside the roster.
- Facebook/phone required; email/Discord optional; contacts and payment evidence private.
- Existing roster min/max and solo rules remain authoritative.
- Guests attach payment proof before submission, as confirmed by the user. No guest edit or later-upload link.
- Rejected entries release player claims; corrections use organizer contact and resubmission.
- Keep submitted institution labels stable and use the existing institution resolver.
- Work in the current IDE checkout on `feat/complete-registration-journey`; no merge or publish.

### Task 1: Backend submission contract

**Files:** `server/registrations/{models,services,serializers,views,admin}.py`, a new migration, registration tests and affected seed/test callers.

**Interfaces:** Add required `submitter_role` (`captain`/`manager`), required `contact_facebook_snapshot`/`contact_phone_snapshot`, optional `contact_email_snapshot`/`contact_discord_snapshot` and `manager_name_snapshot` to submission. Members accept `institution_id` or `institution_label`. Responses keep existing read shape and omit private contacts. Multipart fields are `payload` (JSON registration object), `proof_file` and optional `reference`. JSON remains supported. Paid guests require initial proof; signed-in submitters retain later upload access.

- [x] Write and run failing Django tests for guest/signed-in, roles, contacts, institution snapshots, duplicate claims, rejection/resubmission and atomic guest proof.
- [x] Make submitter nullable, add role/contact snapshots and member institution FK, and widen school snapshot to 255. Preserve historical rows without inventing old contacts.
- [x] Validate roles/contact/roster, resolve institutions after Turnstile, lock the division for duplicate checks and persist snapshots. Link authenticated captain to slot 1 only.
- [x] Accept initial proof and validate before persistence; derive amount/currency; clean stored files after failures. Keep protected reads and owner-only later uploads.
- [x] Expose new private operational fields in read-only organizer admin; adapt existing test and seed callers.
- [x] Run registration tests, migration checks and Django system checks.

### Task 2: Registration form

**Files:** registration API/types, `RosterEditor.svelte`, registration page, EN/VI messages, sign-in callout and affected Vitest/mocked browser tests under `web/`.

**Interfaces:** `submitRegistration(accessToken: string | null, payload, turnstileToken, proofFile?: File, reference?: string)` sends JSON without proof or the multipart envelope from Task 1 with proof. Input members carry institution selection, read members retain `school_snapshot`. Guest success stays on the registration page; signed-in success goes to account detail.

- [x] Write/run failing guest and role form tests.
- [x] Add role/contact sections and manager name; keep captain fixed in slot 1, preserve manager captain selection and roster limits.
- [x] Reuse InstitutionCombobox for each roster row with stable row identity when removing members.
- [x] Add initial proof input for paid divisions, required for guests, with existing image guidance and validation. Preserve inputs after errors and reset Turnstile.
- [x] Add guest confirmation with registration reference and organizer correction instructions, and accurate nonblocking account benefit copy.
- [x] Run focused Vitest and Svelte checks, then format/lint changed files.

### Task 3: Real Django journey verification

**Files:** new dedicated Playwright configuration, browser tests, isolated fixture setup/settings, test-running documentation.

**Interfaces:** Start Django and Svelte with a dedicated test database/media directory. Seed captain, manager, solo and paid divisions plus organizer/participant accounts. Do not mock application API routes.

- [x] Add repeatable fixture setup and isolated Django/Playwright server configuration.
- [x] Exercise guest captain/team, manager/team, solo, signed-in, paid guest proof, organizer review, duplicate rejection and corrected resubmission.
- [x] Verify private proof/contact access and stored institution snapshots through Django tests.
- [x] Run Django suite/migration checks, frontend checks/Vitest and real browser journeys; record exact results.
- [x] Review the combined diff, resolve substantive findings, then mark only verified section-3 items complete.

### Verification findings

The real browser suite exposed a pre-hydration credential-form bug: sign-in could fall back to native GET submission before its client handler attached. Sign-in and account creation must explicitly use POST and keep submission disabled until hydration. Add SSR, hydrated component, and JavaScript-disabled real-browser coverage for this correction.

## Completion evidence

Completed on 2026-09-12. Backend and combined code reviews found no blocking issues; the credential-form correction also passed scoped review. Verification: 136 Django tests, 206 Vitest tests, seven real Django browser tests, three existing browser smoke tests, production build, Svelte checks, migration checks, and changed-file lint/format checks. See [verification notes](../../testing/registration-journey.md) for commands and the remaining Vitest test-server diagnostic. Changes are left in the working tree on `feat/complete-registration-journey`.
