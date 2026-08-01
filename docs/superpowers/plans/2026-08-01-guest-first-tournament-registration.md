# Guest-First Tournament Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Section 3 so tournament registration is guest-first, account-optional, captain/manager aware, contact-aware, and correctly constrained by each division's roster limits.

**Architecture:** Keep Django as the source of truth for registration invariants and use the existing `submit_registration` service as the single write path. Make `Registration.submitted_by` nullable, store per-registration role/contact snapshots on `Registration`, validate roster identity under the existing locked `TournamentGame` transaction, and let the Svelte registration page submit with or without a JWT.

**Tech Stack:** Django 6.0, Django REST Framework 3.17, PostgreSQL-compatible Django models/migrations, SvelteKit 2.63, Svelte 5 runes mode, Paraglide, Tailwind CSS 4, Vitest, Playwright.

## Global Constraints

- Registration is guest-first and locked after submission.
- Guests can submit without creating an account.
- Signed-in users use the same registration form and still record `submitted_by`.
- Account-benefit callouts may appear for guests but must not block or interrupt registration.
- Account conveniences such as saved drafts, saved profile data, account-visible history, and self-serviceable info fixes before submit are deferred until the project is stable.
- Every registration has a per-registration submitter role: `captain` or `manager`.
- Do not add a permanent account role or global role column.
- Captain submitters are roster players, and roster slot 1 is the captain.
- Manager submitters are outside the roster, with manager details collected separately.
- Roster sizing is based on player count only.
- Solo games use `team_size_min = 1` and `team_size_max = 1`.
- Facebook and phone are required private responsible-contact fields.
- Email and Discord are optional private responsible-contact fields.
- Private contact fields must be available to organizers/admin but must not appear in public tournament APIs or participant registration read APIs.
- Enforce one active roster claim per player and division as far as collected roster identity allows.
- Treat `SUBMITTED`, `UNDER_REVIEW`, and `APPROVED` as active; treat `REJECTED` as inactive for duplicate checks.
- Guest submissions do not receive account-dashboard or account-owned payment-proof access in this slice.
- UI strings visible to users must go through Paraglide English/Vietnamese messages.
- Run backend commands from `server/` with `.venv\Scripts\python.exe manage.py`.
- Run frontend commands from `web/` with `pnpm`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `server/registrations/models.py` | Make `submitted_by` nullable; add per-registration submitter role, manager snapshot, and private contact snapshot fields. |
| `server/registrations/migrations/0002_guest_submitter_contact.py` | Persist nullable submitter and new snapshot fields without rewriting historical rows. |
| `server/registrations/services.py` | Accept guest submissions, validate role/contact/captain-slot rules, enforce min/max and duplicate active roster claims. |
| `server/registrations/serializers.py` | Accept the new submission fields while keeping read serializers private-contact safe. |
| `server/registrations/views.py` | Allow unauthenticated `POST /api/registrations/submit/` while keeping list/detail/payment protected. |
| `server/registrations/admin.py` | Show private role/contact fields to organizers in Django Admin. |
| `server/registrations/dev_seed.py` | Update seeded registrations for the new service signature and add captain/manager examples. |
| `server/registrations/tests/test_models.py` | Cover nullable guest submitter and model defaults. |
| `server/registrations/tests/test_services.py` | Cover service-level role/contact/min-max/duplicate/rejected behavior. |
| `server/registrations/tests/test_api.py` | Cover guest submit, authenticated submit, private-field safety, and protected account-only routes. |
| `server/registrations/tests/test_seed_dev_data_command.py` | Keep seed smoke tests aligned with the new required service inputs. |
| `server/tournaments/tests/test_api.py` | Keep public tournament privacy checks aligned with registration-contact non-exposure. |
| `web/src/lib/api/types.ts` | Add submitter role/contact fields to the registration submission DTO. |
| `web/src/lib/api/registrations.ts` | Let `submitRegistration` send an optional JWT and omit auth for guests. |
| `web/src/lib/api/registrations.test.ts` | Verify guest submissions send no `Authorization` header and signed submissions still do. |
| `web/src/lib/components/registrations/RosterEditor.svelte` | Render min-to-max player rows, add/remove controls, and captain locking for captain submitters. |
| `web/src/lib/components/registrations/registration-flow.svelte.spec.ts` | Cover roster min/max controls and captain/manager captain behavior. |
| `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte` | Remove guest redirect, collect submitter role/contact/manager fields, submit guest/signed payloads, show guest-safe confirmation. |
| `web/src/routes/registration-pages.svelte.spec.ts` | Cover route-level guest access, payload shape, signed path, validation, and confirmation copy. |
| `web/src/routes/public-registration.e2e.ts` | Replace the old unauthenticated register redirect smoke with a guest-access smoke. |
| `web/src/routes/auth/sign-in/+page.svelte` | Keep account-benefit copy quiet and non-blocking. |
| `web/messages/en.json` | Add English strings for role/contact/guest confirmation and update the sign-in access note. |
| `web/messages/vi.json` | Add Vietnamese strings for role/contact/guest confirmation and update the sign-in access note. |
| `docs/TODO-general.md` | Check off Section 3 items only after the implementation and verification pass. |

---

### Task 1: Add Guest-Friendly Registration Fields

**Files:**
- Modify: `server/registrations/models.py`
- Create: `server/registrations/migrations/0002_guest_submitter_contact.py`
- Modify: `server/registrations/tests/test_models.py`
- Modify: `server/registrations/tests/test_api.py`
- Modify: `server/registrations/tests/test_admin_actions.py`
- Modify: `server/registrations/tests/test_seed_dev_data_command.py`
- Modify: `server/tournaments/tests/test_api.py`

**Interfaces:**
- Produces: `Registration.SubmitterRole.CAPTAIN == "captain"`
- Produces: `Registration.SubmitterRole.MANAGER == "manager"`
- Produces: nullable `Registration.submitted_by`
- Produces: `Registration.submitter_role`
- Produces: `Registration.manager_name_snapshot`
- Produces: `Registration.contact_facebook_snapshot`
- Produces: `Registration.contact_phone_snapshot`
- Produces: `Registration.contact_email_snapshot`
- Produces: `Registration.contact_discord_snapshot`

- [ ] **Step 1: Write the failing model test**

Add this test to `server/registrations/tests/test_models.py`:

```python
def test_registration_allows_guest_submitter_and_stores_private_contact_snapshot(self):
    registration = Registration.objects.create(
        tournament_game=self.tournament_game,
        submitted_by=None,
        submitter_role=Registration.SubmitterRole.MANAGER,
        manager_name_snapshot="Manager One",
        contact_facebook_snapshot="https://facebook.com/manager.one",
        contact_phone_snapshot="+84901234567",
        contact_email_snapshot="manager@example.com",
        contact_discord_snapshot="manager#0001",
        team_name="",
        status=Registration.Status.SUBMITTED,
        fee_amount_snapshot=Decimal("50000.00"),
        fee_currency_snapshot="VND",
    )

    self.assertIsNone(registration.submitted_by)
    self.assertEqual(registration.submitter_role, Registration.SubmitterRole.MANAGER)
    self.assertEqual(registration.manager_name_snapshot, "Manager One")
    self.assertEqual(registration.contact_facebook_snapshot, "https://facebook.com/manager.one")
    self.assertEqual(registration.contact_phone_snapshot, "+84901234567")
    self.assertEqual(registration.contact_email_snapshot, "manager@example.com")
    self.assertEqual(registration.contact_discord_snapshot, "manager#0001")
```

- [ ] **Step 2: Run the model test to verify it fails**

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_models.RegistrationModelTests.test_registration_allows_guest_submitter_and_stores_private_contact_snapshot -v 2
```

Expected: FAIL because `submitted_by` is required and the new role/contact fields do not exist.

- [ ] **Step 3: Add model fields**

In `server/registrations/models.py`, update `Registration`:

```python
class Registration(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class SubmitterRole(models.TextChoices):
        CAPTAIN = "captain", "Captain"
        MANAGER = "manager", "Manager"

    tournament_game = models.ForeignKey(
        TournamentGame, on_delete=models.PROTECT, related_name="registrations"
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_registrations",
    )
    submitter_role = models.CharField(
        max_length=16,
        choices=SubmitterRole.choices,
        default=SubmitterRole.CAPTAIN,
    )
    manager_name_snapshot = models.CharField(max_length=128, blank=True)
    contact_facebook_snapshot = models.CharField(max_length=200, blank=True)
    contact_phone_snapshot = models.CharField(max_length=32, blank=True)
    contact_email_snapshot = models.EmailField(blank=True)
    contact_discord_snapshot = models.CharField(max_length=100, blank=True)
    team_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    fee_amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    fee_currency_snapshot = models.CharField(max_length=3)
    submitted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

- [ ] **Step 4: Create the migration**

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py makemigrations registrations --name guest_submitter_contact
```

Expected: creates `server/registrations/migrations/0002_guest_submitter_contact.py`.

- [ ] **Step 5: Update direct registration fixtures**

Where tests call `Registration.objects.create(...)`, add explicit role/contact values so fixture meaning stays obvious:

```python
submitter_role=Registration.SubmitterRole.CAPTAIN,
manager_name_snapshot="",
contact_facebook_snapshot="https://facebook.com/captain",
contact_phone_snapshot="+84901234567",
contact_email_snapshot="",
contact_discord_snapshot="",
```

Apply this in:

```text
server/registrations/tests/test_api.py
server/registrations/tests/test_admin_actions.py
server/registrations/tests/test_models.py
server/registrations/tests/test_seed_dev_data_command.py
server/tournaments/tests/test_api.py
```

- [ ] **Step 6: Run model and migration checks**

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_models --keepdb
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Expected: both commands exit `0`; migration check reports no pending model changes.

- [ ] **Step 7: Commit model fields**

```powershell
git add server/registrations/models.py server/registrations/migrations/0002_guest_submitter_contact.py server/registrations/tests/test_models.py server/registrations/tests/test_api.py server/registrations/tests/test_admin_actions.py server/registrations/tests/test_seed_dev_data_command.py server/tournaments/tests/test_api.py
git commit -m "feat: add registration submitter contact fields"
```

---

### Task 2: Enforce Guest, Role, Contact, And Roster Rules In The Service

**Files:**
- Modify: `server/registrations/services.py`
- Modify: `server/registrations/dev_seed.py`
- Modify: `server/registrations/tests/test_services.py`
- Modify: `server/registrations/tests/test_seed_dev_data_command.py`

**Interfaces:**
- Consumes: `Registration.SubmitterRole`
- Produces: `ResponsibleContactInput(facebook: str, phone: str, email: str = "", discord: str = "")`
- Produces: `submit_registration(submitted_by, tournament_game_id, team_name, submitter_role, responsible_contact, members, manager_name_snapshot="")`
- Produces: normalized active roster duplicate checks over `(gamer_tag_snapshot, school_snapshot)` within one `TournamentGame`

- [ ] **Step 1: Add failing service tests for guest and contact snapshots**

In `server/registrations/tests/test_services.py`, import the new dataclass once it exists:

```python
from registrations.services import ResponsibleContactInput
```

Add helper methods inside `RegistrationServiceTests`:

```python
def _contact(self, *, facebook="https://facebook.com/captain", phone="+84901234567"):
    return ResponsibleContactInput(
        facebook=facebook,
        phone=phone,
        email="captain@example.com",
        discord="captain#0001",
    )

def _submit_solo(self, *, submitted_by=None, submitter_role=Registration.SubmitterRole.CAPTAIN):
    return submit_registration(
        submitted_by=submitted_by,
        tournament_game_id=self.tournament_game.pk,
        team_name="",
        submitter_role=submitter_role,
        responsible_contact=self._contact(),
        manager_name_snapshot="",
        members=[self._member()],
    )
```

Add this test:

```python
def test_guest_submission_stores_contact_and_empty_actor(self):
    registration = self._submit_solo(submitted_by=None)

    event = registration.status_events.get()
    self.assertIsNone(registration.submitted_by)
    self.assertIsNone(event.actor)
    self.assertEqual(registration.submitter_role, Registration.SubmitterRole.CAPTAIN)
    self.assertEqual(registration.contact_facebook_snapshot, "https://facebook.com/captain")
    self.assertEqual(registration.contact_phone_snapshot, "+84901234567")
    self.assertEqual(registration.contact_email_snapshot, "captain@example.com")
    self.assertEqual(registration.contact_discord_snapshot, "captain#0001")
```

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_services.RegistrationServiceTests.test_guest_submission_stores_contact_and_empty_actor --keepdb
```

Expected: FAIL because `ResponsibleContactInput` and the new `submit_registration` parameters do not exist.

- [ ] **Step 2: Add failing service tests for captain and manager role rules**

Add:

```python
def test_captain_submitter_must_be_roster_slot_one(self):
    self.tournament_game.team_size_min = 2
    self.tournament_game.team_size_max = 2
    self.tournament_game.registration_capacity = None
    self.tournament_game.save(
        update_fields=("team_size_min", "team_size_max", "registration_capacity")
    )

    with self.assertRaisesMessage(ValidationError, "Captain submitters must be roster slot 1."):
        submit_registration(
            submitted_by=None,
            tournament_game_id=self.tournament_game.pk,
            team_name="Team",
            submitter_role=Registration.SubmitterRole.CAPTAIN,
            responsible_contact=self._contact(),
            manager_name_snapshot="",
            members=[
                self._member(is_captain=False, display_order=1),
                self._member(gamer_tag="captain-two", is_captain=True, display_order=2),
            ],
        )

def test_manager_submitter_requires_manager_name_and_keeps_roster_captain(self):
    registration = submit_registration(
        submitted_by=None,
        tournament_game_id=self.tournament_game.pk,
        team_name="",
        submitter_role=Registration.SubmitterRole.MANAGER,
        responsible_contact=self._contact(),
        manager_name_snapshot=" Manager One ",
        members=[self._member()],
    )

    self.assertEqual(registration.submitter_role, Registration.SubmitterRole.MANAGER)
    self.assertEqual(registration.manager_name_snapshot, "Manager One")
    self.assertTrue(registration.members.get().is_captain)

def test_manager_submitter_rejects_blank_manager_name(self):
    with self.assertRaisesMessage(ValidationError, "Manager name is required."):
        submit_registration(
            submitted_by=None,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            submitter_role=Registration.SubmitterRole.MANAGER,
            responsible_contact=self._contact(),
            manager_name_snapshot=" ",
            members=[self._member()],
        )
```

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_services.RegistrationServiceTests.test_captain_submitter_must_be_roster_slot_one registrations.tests.test_services.RegistrationServiceTests.test_manager_submitter_requires_manager_name_and_keeps_roster_captain registrations.tests.test_services.RegistrationServiceTests.test_manager_submitter_rejects_blank_manager_name --keepdb
```

Expected: FAIL because role rules are not implemented.

- [ ] **Step 3: Add failing service tests for contact and duplicate roster claims**

Add:

```python
def test_contact_requires_facebook_and_phone(self):
    with self.assertRaisesMessage(ValidationError, "Facebook contact is required."):
        submit_registration(
            submitted_by=None,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            submitter_role=Registration.SubmitterRole.CAPTAIN,
            responsible_contact=self._contact(facebook=" "),
            manager_name_snapshot="",
            members=[self._member()],
        )

    with self.assertRaisesMessage(ValidationError, "Phone contact is required."):
        submit_registration(
            submitted_by=None,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            submitter_role=Registration.SubmitterRole.CAPTAIN,
            responsible_contact=self._contact(phone=" "),
            manager_name_snapshot="",
            members=[self._member()],
        )

def test_active_duplicate_roster_claim_is_rejected_but_rejected_entry_can_resubmit(self):
    self.tournament_game.registration_capacity = None
    self.tournament_game.save(update_fields=("registration_capacity",))
    first = self._submit_solo(submitted_by=self.captain)

    with self.assertRaisesMessage(ValidationError, "A player already has an active registration for this division."):
        submit_registration(
            submitted_by=None,
            tournament_game_id=self.tournament_game.pk,
            team_name="",
            submitter_role=Registration.SubmitterRole.CAPTAIN,
            responsible_contact=self._contact(),
            manager_name_snapshot="",
            members=[self._member(gamer_tag=" CAPTAIN ")],
        )

    first.status = Registration.Status.REJECTED
    first.save(update_fields=("status", "updated_at"))

    corrected = submit_registration(
        submitted_by=None,
        tournament_game_id=self.tournament_game.pk,
        team_name="",
        submitter_role=Registration.SubmitterRole.CAPTAIN,
        responsible_contact=self._contact(),
        manager_name_snapshot="",
        members=[self._member(gamer_tag=" captain ")],
    )

    self.assertEqual(corrected.status, Registration.Status.SUBMITTED)
```

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_services.RegistrationServiceTests.test_contact_requires_facebook_and_phone registrations.tests.test_services.RegistrationServiceTests.test_active_duplicate_roster_claim_is_rejected_but_rejected_entry_can_resubmit --keepdb
```

Expected: FAIL because contact and duplicate checks are not implemented.

- [ ] **Step 4: Implement service dataclasses and validation helpers**

In `server/registrations/services.py`, add:

```python
@dataclass(frozen=True)
class ResponsibleContactInput:
    facebook: str
    phone: str
    email: str = ""
    discord: str = ""


def _clean_spaces(value: str) -> str:
    return " ".join(value.strip().split())


def _normalized_player_claim(member: RegistrationMemberInput) -> tuple[str, str]:
    return (
        _clean_spaces(member.gamer_tag_snapshot).casefold(),
        _clean_spaces(member.school_snapshot).casefold(),
    )
```

Replace the `submit_registration` signature with:

```python
def submit_registration(
    *,
    submitted_by,
    tournament_game_id: int,
    team_name: str,
    submitter_role: str,
    responsible_contact: ResponsibleContactInput,
    members: Sequence[RegistrationMemberInput],
    manager_name_snapshot: str = "",
) -> Registration:
```

Call these helpers after capacity and before `Registration.objects.create(...)`:

```python
_validate_roster(
    tournament_game=tournament_game,
    team_name=team_name,
    members=members,
)
_validate_submitter_details(
    submitter_role=submitter_role,
    manager_name_snapshot=manager_name_snapshot,
    responsible_contact=responsible_contact,
    members=members,
)
_validate_roster_claims_available(tournament_game=tournament_game, members=members)
```

Create the registration with:

```python
registration = Registration.objects.create(
    tournament_game=tournament_game,
    submitted_by=submitted_by if getattr(submitted_by, "is_authenticated", False) else None,
    submitter_role=submitter_role,
    manager_name_snapshot=_clean_spaces(manager_name_snapshot),
    contact_facebook_snapshot=responsible_contact.facebook.strip(),
    contact_phone_snapshot=responsible_contact.phone.strip(),
    contact_email_snapshot=responsible_contact.email.strip(),
    contact_discord_snapshot=responsible_contact.discord.strip(),
    team_name=team_name.strip(),
    status=Registration.Status.SUBMITTED,
    fee_amount_snapshot=tournament_game.fee_amount,
    fee_currency_snapshot=tournament_game.fee_currency,
)
```

Keep the status event actor nullable:

```python
actor = submitted_by if getattr(submitted_by, "is_authenticated", False) else None
RegistrationStatusEvent.objects.create(
    registration=registration,
    from_status="",
    to_status=Registration.Status.SUBMITTED,
    actor=actor,
)
```

Add:

```python
def _validate_submitter_details(
    *,
    submitter_role: str,
    manager_name_snapshot: str,
    responsible_contact: ResponsibleContactInput,
    members: Sequence[RegistrationMemberInput],
) -> None:
    if submitter_role not in {
        Registration.SubmitterRole.CAPTAIN,
        Registration.SubmitterRole.MANAGER,
    }:
        raise ValidationError("Submitter role is invalid.")
    if not responsible_contact.facebook.strip():
        raise ValidationError("Facebook contact is required.")
    if not responsible_contact.phone.strip():
        raise ValidationError("Phone contact is required.")
    captain_member = next((member for member in members if member.is_captain), None)
    if submitter_role == Registration.SubmitterRole.CAPTAIN:
        if captain_member is None or captain_member.display_order != 1:
            raise ValidationError("Captain submitters must be roster slot 1.")
        if manager_name_snapshot.strip():
            raise ValidationError("Manager name is only allowed for manager submissions.")
    if submitter_role == Registration.SubmitterRole.MANAGER and not manager_name_snapshot.strip():
        raise ValidationError("Manager name is required.")


def _validate_roster_claims_available(
    *, tournament_game: TournamentGame, members: Sequence[RegistrationMemberInput]
) -> None:
    incoming_claims = [_normalized_player_claim(member) for member in members]
    if len(set(incoming_claims)) != len(incoming_claims):
        raise ValidationError("Each player can appear only once in a roster.")

    active_members = RegistrationMember.objects.filter(
        registration__tournament_game=tournament_game,
        registration__status__in=Registration.active_statuses(),
    ).values_list("gamer_tag_snapshot", "school_snapshot")
    active_claims = {
        (_clean_spaces(gamer_tag).casefold(), _clean_spaces(school).casefold())
        for gamer_tag, school in active_members
    }
    if set(incoming_claims) & active_claims:
        raise ValidationError("A player already has an active registration for this division.")
```

- [ ] **Step 5: Update service call sites and seed data**

Every `submit_registration(...)` call in `server/registrations/dev_seed.py` and `server/registrations/tests/test_services.py` must pass:

```python
submitter_role=Registration.SubmitterRole.CAPTAIN,
responsible_contact=ResponsibleContactInput(
    facebook="https://facebook.com/captain",
    phone="+84901234567",
    email="captain@example.com",
    discord="captain#0001",
),
manager_name_snapshot="",
```

For at least one seeded manager example in `server/registrations/dev_seed.py`, pass:

```python
submitter_role=Registration.SubmitterRole.MANAGER,
responsible_contact=ResponsibleContactInput(
    facebook="https://facebook.com/usec.manager",
    phone="+84909876543",
    email="manager@example.com",
    discord="usec-manager",
),
manager_name_snapshot="USEC Manager",
```

- [ ] **Step 6: Run service and seed tests**

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_services registrations.tests.test_seed_dev_data_command --keepdb
```

Expected: all tests exit `0`.

- [ ] **Step 7: Commit service behavior**

```powershell
git add server/registrations/services.py server/registrations/dev_seed.py server/registrations/tests/test_services.py server/registrations/tests/test_seed_dev_data_command.py
git commit -m "feat: support guest registration service rules"
```

---

### Task 3: Open The Submit API While Preserving Account-Only Routes

**Files:**
- Modify: `server/registrations/serializers.py`
- Modify: `server/registrations/views.py`
- Modify: `server/registrations/admin.py`
- Modify: `server/registrations/tests/test_api.py`
- Modify: `server/tournaments/tests/test_api.py`

**Interfaces:**
- Consumes: `ResponsibleContactInput`
- Produces: unauthenticated `POST /api/registrations/submit/`
- Preserves: authenticated-only `GET /api/registrations/`
- Preserves: authenticated-only `GET /api/registrations/{id}/`
- Preserves: authenticated-only `POST /api/registrations/{id}/payment-attempts/`

- [ ] **Step 1: Write failing API tests**

Update `_submission_payload()` in `server/registrations/tests/test_api.py`:

```python
def _submission_payload(self):
    return {
        "tournament_game": self.tournament_game.pk,
        "team_name": "",
        "submitter_role": Registration.SubmitterRole.CAPTAIN,
        "manager_name_snapshot": "",
        "contact_facebook_snapshot": "https://facebook.com/captain",
        "contact_phone_snapshot": "+84901234567",
        "contact_email_snapshot": "captain@example.com",
        "contact_discord_snapshot": "captain#0001",
        "members": [
            {
                "gamer_tag_snapshot": "captain",
                "school_snapshot": "HCMUS",
                "is_captain": True,
                "display_order": 1,
            }
        ],
    }
```

Add:

```python
def test_guest_can_submit_without_an_account(self):
    payload = self._submission_payload()
    payload["turnstile_token"] = "debug-token"

    response = self.client.post("/api/registrations/submit/", payload, format="json")

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    registration = Registration.objects.get(pk=response.data["id"])
    self.assertIsNone(registration.submitted_by)
    self.assertEqual(registration.submitter_role, Registration.SubmitterRole.CAPTAIN)
    self.assertEqual(registration.contact_facebook_snapshot, "https://facebook.com/captain")
    self.assertEqual(registration.contact_phone_snapshot, "+84901234567")
    self.assertNotIn("contact_facebook_snapshot", response.data)
    self.assertNotIn("contact_phone_snapshot", response.data)
    self.assertNotIn("contact_email_snapshot", response.data)
    self.assertNotIn("contact_discord_snapshot", response.data)

def test_manager_submission_accepts_manager_details(self):
    payload = self._submission_payload()
    payload["submitter_role"] = Registration.SubmitterRole.MANAGER
    payload["manager_name_snapshot"] = "Manager One"
    payload["turnstile_token"] = "debug-token"

    response = self.client.post("/api/registrations/submit/", payload, format="json")

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    registration = Registration.objects.get(pk=response.data["id"])
    self.assertEqual(registration.submitter_role, Registration.SubmitterRole.MANAGER)
    self.assertEqual(registration.manager_name_snapshot, "Manager One")

def test_guest_submit_requires_facebook_and_phone(self):
    missing_facebook = self._submission_payload()
    missing_facebook["contact_facebook_snapshot"] = ""
    missing_phone = self._submission_payload()
    missing_phone["contact_phone_snapshot"] = ""

    facebook_response = self.client.post(
        "/api/registrations/submit/", missing_facebook, format="json"
    )
    phone_response = self.client.post(
        "/api/registrations/submit/", missing_phone, format="json"
    )

    self.assertEqual(facebook_response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("contact_facebook_snapshot", facebook_response.data)
    self.assertEqual(phone_response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("contact_phone_snapshot", phone_response.data)
```

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_api.RegistrationOwnershipApiTests.test_guest_can_submit_without_an_account registrations.tests.test_api.RegistrationOwnershipApiTests.test_manager_submission_accepts_manager_details registrations.tests.test_api.RegistrationOwnershipApiTests.test_guest_submit_requires_facebook_and_phone --keepdb
```

Expected: FAIL because the view still requires authentication and the serializer does not accept new fields.

- [ ] **Step 2: Extend the submission serializer**

In `server/registrations/serializers.py`, import `ResponsibleContactInput`:

```python
from .services import RegistrationMemberInput, ResponsibleContactInput
```

Update `RegistrationSubmissionSerializer`:

```python
class RegistrationSubmissionSerializer(StrictFieldsSerializer):
    tournament_game = serializers.PrimaryKeyRelatedField(
        queryset=TournamentGame.objects.all()
    )
    team_name = serializers.CharField(max_length=100, allow_blank=True)
    submitter_role = serializers.ChoiceField(choices=Registration.SubmitterRole.choices)
    manager_name_snapshot = serializers.CharField(
        max_length=128, allow_blank=True, required=False
    )
    contact_facebook_snapshot = serializers.CharField(max_length=200)
    contact_phone_snapshot = serializers.CharField(max_length=32)
    contact_email_snapshot = serializers.EmailField(allow_blank=True, required=False)
    contact_discord_snapshot = serializers.CharField(
        max_length=100, allow_blank=True, required=False
    )
    members = RegistrationMemberSubmissionSerializer(many=True)
    turnstile_token = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_contact_facebook_snapshot(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Facebook contact is required.")
        return value

    def validate_contact_phone_snapshot(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Phone contact is required.")
        return value

    def to_member_inputs(self) -> list[RegistrationMemberInput]:
        return [
            RegistrationMemberInput(**member) for member in self.validated_data["members"]
        ]

    def to_responsible_contact_input(self) -> ResponsibleContactInput:
        return ResponsibleContactInput(
            facebook=self.validated_data["contact_facebook_snapshot"],
            phone=self.validated_data["contact_phone_snapshot"],
            email=self.validated_data.get("contact_email_snapshot", ""),
            discord=self.validated_data.get("contact_discord_snapshot", ""),
        )
```

- [ ] **Step 3: Make only the submit action public**

In `server/registrations/views.py`, import `AllowAny`:

```python
from rest_framework.permissions import AllowAny, IsAuthenticated
```

Add `get_permissions` to `RegistrationViewSet`:

```python
def get_permissions(self):
    if self.action == "submit":
        return [AllowAny()]
    return [permission() for permission in self.permission_classes]
```

Update `submit`:

```python
submitted_by = request.user if request.user.is_authenticated else None
registration = submit_registration(
    submitted_by=submitted_by,
    tournament_game_id=serializer.validated_data["tournament_game"].pk,
    team_name=serializer.validated_data["team_name"],
    submitter_role=serializer.validated_data["submitter_role"],
    responsible_contact=serializer.to_responsible_contact_input(),
    manager_name_snapshot=serializer.validated_data.get("manager_name_snapshot", ""),
    members=serializer.to_member_inputs(),
)
```

- [ ] **Step 4: Show contact snapshots to organizers in admin**

In `server/registrations/admin.py`, add these fields to `RegistrationAdmin.list_display`:

```python
"submitter_role",
"manager_name_snapshot",
"contact_facebook_snapshot",
"contact_phone_snapshot",
```

Update `search_fields`:

```python
search_fields = (
    "team_name",
    "submitted_by__email",
    "manager_name_snapshot",
    "contact_facebook_snapshot",
    "contact_phone_snapshot",
    "contact_email_snapshot",
    "contact_discord_snapshot",
    "members__gamer_tag_snapshot",
)
```

Keep `get_readonly_fields()` as-is so the new fields are visible but immutable.

- [ ] **Step 5: Confirm public tournament APIs still do not expose contact**

In `server/tournaments/tests/test_api.py`, extend an existing public tournament serialization test with:

```python
self.assertNotIn("contact_facebook_snapshot", str(response.data))
self.assertNotIn("contact_phone_snapshot", str(response.data))
self.assertNotIn("contact_email_snapshot", str(response.data))
self.assertNotIn("contact_discord_snapshot", str(response.data))
```

- [ ] **Step 6: Run API and privacy tests**

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations.tests.test_api tournaments.tests.test_api --keepdb
```

Expected: all tests exit `0`.

- [ ] **Step 7: Commit API behavior**

```powershell
git add server/registrations/serializers.py server/registrations/views.py server/registrations/admin.py server/registrations/tests/test_api.py server/tournaments/tests/test_api.py
git commit -m "feat: open registration submit api to guests"
```

---

### Task 4: Update Frontend API Types And Non-Blocking Account Copy

**Files:**
- Modify: `web/src/lib/api/types.ts`
- Modify: `web/src/lib/api/registrations.ts`
- Modify: `web/src/lib/api/registrations.test.ts`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`
- Modify: `web/src/routes/auth/sign-in/+page.svelte`

**Interfaces:**
- Produces: `RegistrationSubmitterRole = "captain" | "manager"`
- Produces: extended `RegistrationSubmissionPayload`
- Produces: `submitRegistration(accessToken: string | null, payload, turnstileToken)`

- [ ] **Step 1: Write failing frontend API tests**

In `web/src/lib/api/registrations.test.ts`, add or update payload setup:

```ts
const payload = {
	tournament_game: 9,
	team_name: 'Team Blue',
	submitter_role: 'captain' as const,
	manager_name_snapshot: '',
	contact_facebook_snapshot: 'https://facebook.com/captain',
	contact_phone_snapshot: '+84901234567',
	contact_email_snapshot: '',
	contact_discord_snapshot: '',
	members: [
		{
			gamer_tag_snapshot: 'captain',
			school_snapshot: 'HCMUS',
			is_captain: true,
			display_order: 1
		}
	]
};
```

Add:

```ts
it('omits authorization when submitting as a guest', async () => {
	const fetcher = vi.fn(async () => new Response(JSON.stringify({ id: 1 }), { status: 201 }));

	await submitRegistration(null, payload, 'turnstile-token', {
		baseUrl: 'https://api.example.test',
		fetcher
	});

	const [, init] = fetcher.mock.calls[0];
	expect(new Headers(init?.headers).has('authorization')).toBe(false);
	expect(JSON.parse(String(init?.body))).toMatchObject({
		submitter_role: 'captain',
		contact_facebook_snapshot: 'https://facebook.com/captain',
		contact_phone_snapshot: '+84901234567',
		turnstile_token: 'turnstile-token'
	});
});

it('keeps authorization when submitting as a signed-in user', async () => {
	const fetcher = vi.fn(async () => new Response(JSON.stringify({ id: 1 }), { status: 201 }));

	await submitRegistration('access-token', payload, 'turnstile-token', {
		baseUrl: 'https://api.example.test',
		fetcher
	});

	const [, init] = fetcher.mock.calls[0];
	expect(new Headers(init?.headers).get('authorization')).toBe('Bearer access-token');
});
```

Run from `web/`:

```powershell
pnpm exec vitest run --project client src/lib/api/registrations.test.ts
```

Expected: FAIL because `submitRegistration` still requires a non-null token and does not accept request overrides if that test helper is not already present.

- [ ] **Step 2: Extend TypeScript DTOs**

In `web/src/lib/api/types.ts`, replace `RegistrationSubmissionPayload` with:

```ts
export type RegistrationSubmitterRole = 'captain' | 'manager';

export interface RegistrationSubmissionPayload {
	tournament_game: number;
	team_name: string;
	submitter_role: RegistrationSubmitterRole;
	manager_name_snapshot: string;
	contact_facebook_snapshot: string;
	contact_phone_snapshot: string;
	contact_email_snapshot: string;
	contact_discord_snapshot: string;
	members: RegistrationMemberInput[];
}
```

- [ ] **Step 3: Let `submitRegistration` use an optional token**

In `web/src/lib/api/registrations.ts`, import `ApiRequestOptions`:

```ts
import { requestJson, type ApiRequestOptions } from './client';
```

Replace `submitRegistration` with:

```ts
export function submitRegistration(
	accessToken: string | null,
	payload: RegistrationSubmissionPayload,
	turnstileToken: string,
	options: Pick<ApiRequestOptions, 'baseUrl' | 'fetcher'> = {}
) {
	return requestJson<RegistrationRead>('/registrations/submit/', {
		...options,
		method: 'POST',
		accessToken,
		body: { ...payload, turnstile_token: turnstileToken }
	});
}
```

- [ ] **Step 4: Add messages for role/contact/guest confirmation**

Add these keys to `web/messages/en.json`:

```json
"registration_account_benefit_note": "Create an account later if you want your registrations and profile details tied to one place.",
"registration_guest_confirmation_heading": "Registration submitted",
"registration_guest_confirmation_body": "Your registration is locked after submission. If anything is wrong, contact USEC through Facebook first, then email or Discord.",
"registration_submitter_role_heading": "Who is submitting this registration?",
"registration_submitter_role_captain": "Captain",
"registration_submitter_role_manager": "Manager",
"registration_submitter_role_captain_note": "Slot 1 is you and is locked as captain.",
"registration_submitter_role_manager_note": "You are managing the team and are not counted as a player.",
"registration_manager_heading": "Manager details",
"field_manager_name": "Manager name",
"registration_contact_heading": "Responsible contact",
"registration_contact_note": "Facebook and phone are private organizer contact fields.",
"field_facebook": "Facebook",
"field_phone": "Phone",
"field_discord": "Discord",
"roster_add_player": "Add player",
"roster_remove_player": "Remove player {number}",
"roster_slot_one_locked_captain": "Slot 1 captain"
```

Add Vietnamese equivalents to `web/messages/vi.json` with the same keys:

```json
"registration_account_benefit_note": "Bạn có thể tạo tài khoản sau nếu muốn lưu đăng ký và thông tin hồ sơ ở một nơi.",
"registration_guest_confirmation_heading": "Đã gửi đăng ký",
"registration_guest_confirmation_body": "Đăng ký sẽ được khóa sau khi gửi. Nếu có sai sót, hãy liên hệ USEC qua Facebook trước, rồi email hoặc Discord.",
"registration_submitter_role_heading": "Bạn gửi đăng ký này với vai trò nào?",
"registration_submitter_role_captain": "Đội trưởng",
"registration_submitter_role_manager": "Quản lý",
"registration_submitter_role_captain_note": "Vị trí 1 là bạn và được khóa là đội trưởng.",
"registration_submitter_role_manager_note": "Bạn quản lý đội và không được tính là tuyển thủ.",
"registration_manager_heading": "Thông tin quản lý",
"field_manager_name": "Tên quản lý",
"registration_contact_heading": "Liên hệ phụ trách",
"registration_contact_note": "Facebook và số điện thoại là thông tin riêng để ban tổ chức liên hệ.",
"field_facebook": "Facebook",
"field_phone": "Số điện thoại",
"field_discord": "Discord",
"roster_add_player": "Thêm tuyển thủ",
"roster_remove_player": "Xóa tuyển thủ {number}",
"roster_slot_one_locked_captain": "Vị trí 1 đội trưởng"
```

Update `auth_access_note` in both message files so it names account benefits without implying an account is required:

```json
"auth_access_note": "Sign in to view account-only pages. Tournament registration can still be submitted as a guest from the tournament page."
```

```json
"auth_access_note": "Đăng nhập để xem các trang chỉ dành cho tài khoản. Bạn vẫn có thể đăng ký giải với tư cách khách từ trang giải đấu."
```

- [ ] **Step 5: Keep the sign-in callout quiet**

In `web/src/routes/auth/sign-in/+page.svelte`, keep the existing `m.auth_access_note()` placement. Do not add modals, redirects, or blocking banners from the registration page to sign-in.

- [ ] **Step 6: Run frontend API and i18n checks**

Run from `web/`:

```powershell
pnpm exec vitest run --project client src/lib/api/registrations.test.ts
pnpm check
```

Expected: both commands exit `0`.

- [ ] **Step 7: Commit API types and copy**

```powershell
git add web/src/lib/api/types.ts web/src/lib/api/registrations.ts web/src/lib/api/registrations.test.ts web/messages/en.json web/messages/vi.json web/src/routes/auth/sign-in/+page.svelte
git commit -m "feat: type guest registration payloads"
```

---

### Task 5: Make RosterEditor Respect Min/Max And Captain Locking

**Files:**
- Modify: `web/src/lib/components/registrations/RosterEditor.svelte`
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`

**Interfaces:**
- Consumes: `RegistrationSubmitterRole`
- Produces: `RosterEditor` props `{ teamSizeMin, teamSizeMax, submitterRole, members }`
- Produces: add/remove rows between `teamSizeMin` and `teamSizeMax`
- Produces: locked slot 1 captain when `submitterRole === "captain"`

- [ ] **Step 1: Write failing RosterEditor tests**

In `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`, update RosterEditor renders to pass `submitterRole`.

Add:

```ts
it('starts at minimum size and can add players up to the maximum', async () => {
	const members = $state([]);
	render(RosterEditor, {
		props: {
			teamSizeMin: 2,
			teamSizeMax: 4,
			submitterRole: 'manager',
			members
		}
	});

	expect(page.getAllByText(/Member/)).toHaveLength(2);
	await page.getByRole('button', { name: 'Add player' }).click();
	await page.getByRole('button', { name: 'Add player' }).click();
	expect(page.getAllByText(/Member/)).toHaveLength(4);
	await expect.element(page.getByRole('button', { name: 'Add player' })).toBeDisabled();
});

it('does not remove below the minimum roster size', async () => {
	const members = $state([]);
	render(RosterEditor, {
		props: {
			teamSizeMin: 2,
			teamSizeMax: 3,
			submitterRole: 'manager',
			members
		}
	});

	await expect.element(page.getByRole('button', { name: 'Remove player 1' })).toBeDisabled();
	await expect.element(page.getByRole('button', { name: 'Remove player 2' })).toBeDisabled();
});

it('locks slot one as captain for captain submitters', async () => {
	const members = $state([]);
	render(RosterEditor, {
		props: {
			teamSizeMin: 2,
			teamSizeMax: 2,
			submitterRole: 'captain',
			members
		}
	});

	expect(members[0].is_captain).toBe(true);
	expect(members[1].is_captain).toBe(false);
	expect(page.queryByRole('radio', { name: 'Set member 2 as captain' })).toBeNull();
	expect(page.getByText('Slot 1 captain')).toBeTruthy();
});
```

Run from `web/`:

```powershell
pnpm exec vitest run --project client src/lib/components/registrations/registration-flow.svelte.spec.ts
```

Expected: FAIL because `submitterRole`, add/remove controls, and captain locking do not exist.

- [ ] **Step 2: Update RosterEditor props and helpers**

In `web/src/lib/components/registrations/RosterEditor.svelte`, update imports:

```svelte
<script lang="ts">
	import { Plus, Trash2 } from 'lucide-svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import type { RegistrationMemberInput, RegistrationSubmitterRole } from '$lib/api/types';
```

Use this props shape:

```ts
interface Props {
	teamSizeMin: number;
	teamSizeMax: number;
	submitterRole: RegistrationSubmitterRole;
	members?: RegistrationMemberInput[];
}

let { teamSizeMin, teamSizeMax, submitterRole, members = $bindable([]) }: Props = $props();
```

Add helpers:

```ts
function createMember(displayOrder: number): RegistrationMemberInput {
	return {
		gamer_tag_snapshot: '',
		school_snapshot: '',
		is_captain: submitterRole === 'captain' && displayOrder === 1,
		display_order: displayOrder
	};
}

function normalizeMembers(nextMembers: RegistrationMemberInput[]): RegistrationMemberInput[] {
	const normalized = nextMembers.map((member, index) => ({
		...member,
		display_order: index + 1,
		is_captain:
			submitterRole === 'captain'
				? index === 0
				: nextMembers.some((item) => item.is_captain)
					? member.is_captain
					: index === 0
	}));
	if (submitterRole === 'manager' && normalized.filter((member) => member.is_captain).length !== 1) {
		return normalized.map((member, index) => ({ ...member, is_captain: index === 0 }));
	}
	return normalized;
}

function initializeMembers(): void {
	if (members.length === 0) {
		members = Array.from({ length: teamSizeMin }, (_, index) => createMember(index + 1));
		return;
	}
	members = normalizeMembers(members.slice(0, teamSizeMax));
}

function addMember(): void {
	if (members.length >= teamSizeMax) return;
	members = normalizeMembers([...members, createMember(members.length + 1)]);
}

function removeMember(index: number): void {
	if (members.length <= teamSizeMin) return;
	members = normalizeMembers(members.filter((_, memberIndex) => memberIndex !== index));
}

function selectCaptain(selectedIndex: number): void {
	if (submitterRole === 'captain') return;
	members = members.map((member, index) => ({
		...member,
		is_captain: index === selectedIndex
	}));
}
```

- [ ] **Step 3: Update the RosterEditor markup**

Keep existing fields, but render controls after each row and a footer add button.

For the captain control column:

```svelte
{#if submitterRole === 'captain'}
	<div class="flex min-h-11 items-center border px-3 text-sm">
		{index === 0 ? m.roster_slot_one_locked_captain() : m.roster_captain()}
	</div>
{:else}
	<Field.Label class="flex min-h-11 items-center gap-2 border px-3">
		<RadioGroup.Item
			value={String(index)}
			aria-label={m.roster_set_captain({ number: index + 1 })}
		/>
		<span>{m.roster_captain()}</span>
		<span class="sr-only">{m.roster_set_captain({ number: index + 1 })}</span>
	</Field.Label>
{/if}
```

Add the remove button in each row:

```svelte
<Button
	type="button"
	variant="outline"
	size="icon"
	disabled={members.length <= teamSizeMin}
	aria-label={m.roster_remove_player({ number: index + 1 })}
	onclick={() => removeMember(index)}
>
	<Trash2 class="size-4" aria-hidden="true" />
</Button>
```

Add the footer:

```svelte
<div class="mt-4 flex justify-end">
	<Button type="button" variant="outline" disabled={members.length >= teamSizeMax} onclick={addMember}>
		<Plus class="size-4" aria-hidden="true" />
		{m.roster_add_player()}
	</Button>
</div>
```

- [ ] **Step 4: Run component tests and Svelte checks**

Run from `web/`:

```powershell
pnpm exec vitest run --project client src/lib/components/registrations/registration-flow.svelte.spec.ts
pnpm check
```

Expected: both commands exit `0`.

- [ ] **Step 5: Commit roster editor behavior**

```powershell
git add web/src/lib/components/registrations/RosterEditor.svelte web/src/lib/components/registrations/registration-flow.svelte.spec.ts
git commit -m "feat: respect registration roster limits"
```

---

### Task 6: Make The Registration Page Guest-First

**Files:**
- Modify: `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- Modify: `web/src/routes/registration-pages.svelte.spec.ts`
- Modify: `web/src/routes/public-registration.e2e.ts`

**Interfaces:**
- Consumes: `submitRegistration(accessToken: string | null, payload, turnstileToken)`
- Consumes: `RosterEditor` `submitterRole`
- Produces: guest-accessible registration page
- Produces: role/contact/manager form sections
- Produces: guest-safe confirmation after submit

- [ ] **Step 1: Write failing route tests**

In `web/src/routes/registration-pages.svelte.spec.ts`, replace the old unauthenticated redirect expectation with:

```ts
it('keeps guest visitors on the registration page', async () => {
	mockGetAccessToken.mockReturnValue(null);

	render(RegisterPage, { props: { data: registerPageData } });

	await expect.element(page.getByRole('heading', { name: /Register/i })).toBeInTheDocument();
	expect(mockReplaceInternalLocation).not.toHaveBeenCalled();
	expect(page.getByRole('radio', { name: 'Captain' })).toBeTruthy();
	expect(page.getByRole('radio', { name: 'Manager' })).toBeTruthy();
});
```

Add:

```ts
it('submits a guest captain payload and shows guest confirmation', async () => {
	mockGetAccessToken.mockReturnValue(null);
	mockSubmitRegistration.mockResolvedValue({ id: 123, ...registrationReadFixture });

	render(RegisterPage, { props: { data: registerPageData } });

	await page.getByLabelText('Facebook').fill('https://facebook.com/captain');
	await page.getByLabelText('Phone').fill('+84901234567');
	await page.getByLabelText('Gamer tag').nth(0).fill('captain');
	await page.getByLabelText('School').nth(0).fill('HCMUS');
	await solveTurnstile();
	await page.getByRole('button', { name: /Submit/i }).click();

	expect(mockSubmitRegistration).toHaveBeenCalledWith(
		null,
		expect.objectContaining({
			submitter_role: 'captain',
			manager_name_snapshot: '',
			contact_facebook_snapshot: 'https://facebook.com/captain',
			contact_phone_snapshot: '+84901234567',
			members: expect.arrayContaining([
				expect.objectContaining({ display_order: 1, is_captain: true })
			])
		}),
		'turnstile-token'
	);
	expect(mockGoto).not.toHaveBeenCalled();
	await expect.element(page.getByRole('heading', { name: 'Registration submitted' })).toBeInTheDocument();
});

it('collects manager details outside the roster', async () => {
	mockGetAccessToken.mockReturnValue(null);
	mockSubmitRegistration.mockResolvedValue({ id: 124, ...registrationReadFixture });

	render(RegisterPage, { props: { data: registerPageData } });

	await page.getByRole('radio', { name: 'Manager' }).click();
	await page.getByLabelText('Manager name').fill('Manager One');
	await page.getByLabelText('Facebook').fill('https://facebook.com/manager');
	await page.getByLabelText('Phone').fill('+84901234567');
	await page.getByLabelText('Gamer tag').nth(0).fill('captain');
	await page.getByLabelText('School').nth(0).fill('HCMUS');
	await solveTurnstile();
	await page.getByRole('button', { name: /Submit/i }).click();

	expect(mockSubmitRegistration).toHaveBeenCalledWith(
		null,
		expect.objectContaining({
			submitter_role: 'manager',
			manager_name_snapshot: 'Manager One'
		}),
		'turnstile-token'
	);
});
```

Run from `web/`:

```powershell
pnpm exec vitest run --project client src/routes/registration-pages.svelte.spec.ts
```

Expected: FAIL because guests still redirect and the form lacks role/contact fields.

- [ ] **Step 2: Update route state**

In `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`, remove `navigateToSignIn(false)` from `onMount` and set loading false for everyone:

```ts
let submitterRole = $state<RegistrationSubmitterRole>('captain');
let managerName = $state('');
let contactFacebook = $state('');
let contactPhone = $state('');
let contactEmail = $state('');
let contactDiscord = $state('');
let submittedRegistration = $state<RegistrationRead | null>(null);

onMount(() => {
	accessToken = getAccessToken();
	loading = false;
});
```

Import the new types:

```ts
import type {
	RegistrationMemberInput,
	RegistrationRead,
	RegistrationSubmitterRole
} from '$lib/api/types';
```

- [ ] **Step 3: Update submit behavior**

Replace the access-token guard:

```ts
if (submitting) return;
```

Build the payload:

```ts
const registration = await submitRegistration(
	accessToken,
	{
		tournament_game: data.game.id,
		team_name: data.game.team_size_max > 1 ? teamName : '',
		submitter_role: submitterRole,
		manager_name_snapshot: submitterRole === 'manager' ? managerName : '',
		contact_facebook_snapshot: contactFacebook,
		contact_phone_snapshot: contactPhone,
		contact_email_snapshot: contactEmail,
		contact_discord_snapshot: contactDiscord,
		members
	},
	turnstileToken
);
turnstileWidget?.reset();
if (accessToken) {
	await goto(resolve(localizeInternalHref(`/account/registrations/${registration.id}`)));
	return;
}
submittedRegistration = registration;
turnstileToken = '';
```

Keep authentication-error handling for signed-in expired sessions:

```ts
if (isAuthenticationError(cause) && accessToken) {
	navigateToSignIn(true);
	return;
}
```

- [ ] **Step 4: Add the guest-safe confirmation view**

Before the form, render:

```svelte
{#if submittedRegistration}
	<Card.Root class="mt-8">
		<Card.Header>
			<Card.Title><h2>{m.registration_guest_confirmation_heading()}</h2></Card.Title>
			<Card.Description>{m.registration_guest_confirmation_body()}</Card.Description>
		</Card.Header>
		<Card.Content class="text-sm text-(--text-muted)">
			<p>{data.tournament.name} - {data.game.game_name}</p>
			{#if submittedRegistration.team_name}
				<p>{submittedRegistration.team_name}</p>
			{/if}
		</Card.Content>
	</Card.Root>
{:else if loading || redirecting}
```

Do not link guests to `/account/registrations/{id}`.

- [ ] **Step 5: Add role, manager, and contact sections to the form**

Before `RosterEditor`, add a small non-blocking guest callout:

```svelte
{#if !accessToken}
	<p class="border border-(--line) bg-(--surface-muted) p-4 text-sm text-(--text-muted)">
		{m.registration_account_benefit_note()}
	</p>
{/if}
```

Add the role radio group:

```svelte
<Card.Root aria-labelledby="submitter-role-heading">
	<Card.Header>
		<Card.Title><h2 id="submitter-role-heading">{m.registration_submitter_role_heading()}</h2></Card.Title>
	</Card.Header>
	<Card.Content class="grid gap-3 sm:grid-cols-2">
		<label class="flex gap-3 border border-(--line) p-4">
			<input bind:group={submitterRole} type="radio" value="captain" />
			<span>
				<span class="block font-semibold">{m.registration_submitter_role_captain()}</span>
				<span class="block text-sm text-(--text-muted)">{m.registration_submitter_role_captain_note()}</span>
			</span>
		</label>
		<label class="flex gap-3 border border-(--line) p-4">
			<input bind:group={submitterRole} type="radio" value="manager" />
			<span>
				<span class="block font-semibold">{m.registration_submitter_role_manager()}</span>
				<span class="block text-sm text-(--text-muted)">{m.registration_submitter_role_manager_note()}</span>
			</span>
		</label>
	</Card.Content>
</Card.Root>
```

Add manager details only when needed:

```svelte
{#if submitterRole === 'manager'}
	<Card.Root aria-labelledby="manager-heading">
		<Card.Header>
			<Card.Title><h2 id="manager-heading">{m.registration_manager_heading()}</h2></Card.Title>
		</Card.Header>
		<Card.Content>
			<Field
				label={m.field_manager_name()}
				name="manager_name_snapshot"
				required
				maxlength={128}
				error={fieldErrors.manager_name_snapshot?.[0]}
				bind:value={managerName}
			/>
		</Card.Content>
	</Card.Root>
{/if}
```

Add contact fields:

```svelte
<Card.Root aria-labelledby="contact-heading">
	<Card.Header>
		<Card.Title><h2 id="contact-heading">{m.registration_contact_heading()}</h2></Card.Title>
		<Card.Description>{m.registration_contact_note()}</Card.Description>
	</Card.Header>
	<Card.Content class="grid gap-4 sm:grid-cols-2">
		<Field label={m.field_facebook()} name="contact_facebook_snapshot" required maxlength={200} error={fieldErrors.contact_facebook_snapshot?.[0]} bind:value={contactFacebook} />
		<Field label={m.field_phone()} name="contact_phone_snapshot" required maxlength={32} error={fieldErrors.contact_phone_snapshot?.[0]} bind:value={contactPhone} />
		<Field label={m.field_email()} name="contact_email_snapshot" type="email" maxlength={254} error={fieldErrors.contact_email_snapshot?.[0]} bind:value={contactEmail} />
		<Field label={m.field_discord()} name="contact_discord_snapshot" maxlength={100} error={fieldErrors.contact_discord_snapshot?.[0]} bind:value={contactDiscord} />
	</Card.Content>
</Card.Root>
```

Pass role into roster:

```svelte
<RosterEditor
	teamSizeMin={data.game.team_size_min}
	teamSizeMax={data.game.team_size_max}
	submitterRole={submitterRole}
	bind:members
/>
```

- [ ] **Step 6: Update Playwright smoke**

In `web/src/routes/public-registration.e2e.ts`, replace the test named `client navigation to register redirects an unauthenticated visitor to sign in` with:

```ts
test('client navigation to register keeps an unauthenticated visitor on the guest form', async ({
	page
}) => {
	await page.route('**/api/tournaments/', async (route) => {
		await route.fulfill({ json: [tournament] });
	});
	await page.route('**/api/tournaments/usec-summer-2026/', async (route) => {
		await route.fulfill({ json: tournament });
	});

	await page.goto('/auth/sign-in');
	await page.locator('a[href="/"]').first().click();
	await page.getByRole('link', { name: tournament.name }).first().click();
	await page.locator('a[href="/tournaments/usec-summer-2026/games/9/register"]').click();

	await expect(page).toHaveURL('/tournaments/usec-summer-2026/games/9/register');
	await expect(page.getByRole('radio', { name: 'Captain' })).toBeVisible();
	await expect(page.getByLabel('Facebook')).toBeVisible();
	await expect(page.getByLabel('Phone')).toBeVisible();
});
```

- [ ] **Step 7: Run route tests and Svelte checks**

Run from `web/`:

```powershell
pnpm exec vitest run --project client src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts
pnpm check
```

Expected: all commands exit `0`.

- [ ] **Step 8: Commit guest-first page**

```powershell
git add web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte web/src/routes/registration-pages.svelte.spec.ts web/src/routes/public-registration.e2e.ts
git commit -m "feat: make registration form guest first"
```

---

### Task 7: Final Verification And TODO Closure

**Files:**
- Modify: `docs/TODO-general.md`
- Modify: implementation files only if verification exposes a concrete defect

**Interfaces:**
- Confirms Section 3 behavior across backend, frontend, migrations, and docs.
- Produces checked Section 3 TODO items after all implementation tests pass.

- [ ] **Step 1: Run focused backend verification**

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py test registrations --keepdb
.venv\Scripts\python.exe manage.py test tournaments.tests.test_api --keepdb
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Expected: all commands exit `0`; migration check reports no pending model changes.

- [ ] **Step 2: Run focused frontend verification**

Run from `web/`:

```powershell
pnpm exec vitest run --project client src/lib/api/registrations.test.ts src/lib/components/registrations/registration-flow.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts
pnpm check
```

Expected: all commands exit `0`.

- [ ] **Step 3: Run broader project checks**

Run from repo root and app directories:

```powershell
git status --short
```

Run from `server/`:

```powershell
.venv\Scripts\python.exe manage.py check
```

Run from `web/`:

```powershell
pnpm exec vitest run --project client
pnpm check
```

Expected: all commands exit `0`; `git status --short` shows only intentional Section 3 changes.

- [ ] **Step 4: Update Section 3 TODO items**

After all checks pass, mark these items checked in `docs/TODO-general.md`:

```markdown
- [x] Allow unauthenticated accounts to register to the tournaments.
- [x] Advertisements/callouts for account registration (benefits) on [signin page](../web/src/routes/auth/sign-in/+page.svelte) `m.auth_access_note()`) and other suitable places. (note: don't be intrusive.)
- [x] Keep the tournament registration form accessible to authenticated accounts.
- [x] Ask whether the submitter is acting as captain or manager for each sign-up.
- [x] Do not add a permanent account role or role database column.
- [x] Link a captain submitter to roster slot 1 for that registration.
- [x] Keep manager submitters outside the roster.
- [x] Collect private captain contact information.
- [x] Support actual minimum/maximum roster sizes instead of always forcing the maximum.
- [x] Handle solo entrants consistently.
- [x] Enforce one active entry per claimed player and division.
- [x] Define safe behavior for rejected entries, corrections, and resubmission.
- [x] Keep historical roster and institution snapshots stable.
```

- [ ] **Step 5: Commit final Section 3 closure**

```powershell
git add docs/TODO-general.md
git commit -m "docs: close guest registration section"
```

If verification required implementation fixes, commit those fixes in the task that introduced the defect before this docs-only commit.

---

## Self-Review

- Spec coverage: Guest submit, signed submit, captain/manager role, no global role, slot 1 captain, manager outside roster, required Facebook/phone, optional email/Discord, min/max roster sizing, solo min/max, active duplicate claims, rejected resubmission, contact privacy, locked guest correction workflow, and deferred account convenience are each mapped to a task.
- Marker scan: No unresolved red-flag markers remain; `TODO` appears only as the real `docs/TODO-general.md` filename and final TODO-closure task label.
- Type consistency: The model, serializer, service, frontend DTO, and page payload all use `submitter_role`, `manager_name_snapshot`, `contact_facebook_snapshot`, `contact_phone_snapshot`, `contact_email_snapshot`, and `contact_discord_snapshot`.
- Deferred note handling: The line 35 product-decision note is represented as a non-blocking account-benefit copy update and an explicit global constraint; saved drafts and self-service fixes before submit are not implemented in this slice.
