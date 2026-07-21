# Account institution catalogue implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace account-level school text with a PostgreSQL institution catalogue, support nonblocking custom institutions, and complete the minimal account identity contract.

**Architecture:** The `accounts` app owns a shared `Institution` model, a catalogue import command, institution resolution, and the public search endpoint. `User` references an institution, while account serializers accept either a catalogue identifier or a free-text label. Svelte registration and profile views use a reusable combobox; tournament roster snapshots stay independent from accounts.

**Tech Stack:** Django 6, Django REST Framework, PostgreSQL, Python `unittest`, Svelte 5, SvelteKit, TypeScript, Vitest, Playwright browser mode, Paraglide, pnpm, uv

## Global constraints

- New public accounts require first name, last name, email, password, and an institution choice
- `student_id` is staff-only auditing data and must never appear in public or self-service account APIs
- A selected catalogue institution is canonical and verified; a non-empty free-text label creates or reuses a shared pending institution without blocking the account
- The API serializes institutions as `value`, `label`, `code`, `shortName`, `eng`, `type`, and `location`
- Do not redesign tournament roster snapshots or add persistent game identities in this plan
- Keep institution search server-backed; never ship `server/university.json` to every browser
- Do not expand or complete the separately deferred development-seed feature

---

## Planned file structure

| Path | Responsibility |
| --- | --- |
| `server/accounts/models.py` | `Institution`, the `User.institution` relation, and staff-only student-ID validation |
| `server/accounts/services/institutions.py` | Label normalization and canonical/custom institution resolution |
| `server/accounts/management/commands/import_institutions.py` | Idempotent import of `server/university.json` |
| `server/accounts/serializers.py` | Institution response and account input serializers |
| `server/accounts/views.py` and `server/accounts/urls.py` | Public search and existing account endpoints |
| `server/accounts/admin.py` | Institution review and private staff reference administration |
| `server/accounts/migrations/0003_institution_catalogue.py` | Institution table, user relation, and old-school data migration |
| `web/src/lib/api/types.ts` and `web/src/lib/api/institutions.ts` | Shared institution types, account inputs, and search client |
| `web/src/lib/components/forms/InstitutionCombobox.svelte` | Search, selection, free-text fallback, keyboard behavior, and errors |
| `web/src/routes/auth/register/+page.svelte` and `web/src/routes/account/profile/+page.svelte` | Account creation and profile editing |
| `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte` | Remove account-profile defaults while retaining roster snapshots |
| `web/messages/en.json` and `web/messages/vi.json` | Institution-combobox and corrected account copy |

### Task 1: Add the institution domain model and account migration

**Files:**
- Create: `server/accounts/services/__init__.py`
- Create: `server/accounts/services/institutions.py`
- Create: `server/accounts/migrations/0003_institution_catalogue.py`
- Modify: `server/accounts/models.py`
- Modify: `server/accounts/managers.py`
- Modify: `server/accounts/admin.py`
- Create: `server/accounts/tests/test_institutions.py`
- Modify: `server/accounts/tests/test_models.py`

**Interfaces:**
- Produces: `Institution`, `normalize_institution_label(value: str) -> str`, and `resolve_institution(*, institution_id: int | None, institution_label: str | None) -> Institution`
- Produces: `User.institution: ForeignKey[Institution]` and private `User.student_id: str`

- [ ] **Step 1: Write model and resolution tests before creating the model**

```python
class InstitutionResolutionTests(TestCase):
    def test_custom_label_is_normalized_and_reused(self):
        first = resolve_institution(institution_id=None, institution_label="  HCMUS  ")
        second = resolve_institution(institution_id=None, institution_label="hcmus")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.source, Institution.Source.CUSTOM)
        self.assertEqual(first.review_status, Institution.ReviewStatus.PENDING)
        self.assertEqual(first.label, "HCMUS")

    def test_catalogue_label_wins_over_a_new_custom_record(self):
        catalogue = Institution.objects.create(
            value="227", label="University of Science", source=Institution.Source.CATALOGUE
        )
        resolved = resolve_institution(institution_id=None, institution_label=" university of science ")

        self.assertEqual(resolved.pk, catalogue.pk)
```

- [ ] **Step 2: Run the new tests and confirm the missing imports fail**

Run: `uv run python manage.py test accounts.tests.test_institutions -v 2`

Expected: FAIL because `Institution` and `resolve_institution` do not exist.

- [ ] **Step 3: Add `Institution`, normalization, and staff-ID validation**

```python
class Institution(models.Model):
    class Source(models.TextChoices):
        CATALOGUE = "CATALOGUE", "Catalogue"
        CUSTOM = "CUSTOM", "Custom"

    class ReviewStatus(models.TextChoices):
        VERIFIED = "VERIFIED", "Verified"
        PENDING = "PENDING", "Pending"
        REJECTED = "REJECTED", "Rejected"

    value = models.CharField(max_length=32, blank=True)
    label = models.CharField(max_length=255)
    normalized_label = models.CharField(max_length=255, db_index=True)
    code = models.CharField(max_length=64, blank=True)
    short_name = models.CharField(max_length=255, blank=True)
    english_name = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=16, choices=Source, default=Source.CUSTOM)
    review_status = models.CharField(max_length=16, choices=ReviewStatus, default=ReviewStatus.PENDING)
```

```python
def normalize_institution_label(value: str) -> str:
    return " ".join(value.split()).casefold()

def resolve_institution(*, institution_id: int | None, institution_label: str | None) -> Institution:
    if bool(institution_id) == bool(institution_label and institution_label.strip()):
        raise ValidationError("Choose a catalogue institution or enter a custom label.")
    if institution_id:
        return Institution.objects.get(pk=institution_id, source=Institution.Source.CATALOGUE)
    label = " ".join(institution_label.split())
    normalized = normalize_institution_label(label)
    return Institution.objects.filter(
        source=Institution.Source.CATALOGUE, normalized_label=normalized
    ).first() or Institution.objects.get_or_create(
        source=Institution.Source.CUSTOM,
        normalized_label=normalized,
        defaults={"label": label, "review_status": Institution.ReviewStatus.PENDING},
    )[0]
```

Add `institution = models.ForeignKey(Institution, null=True, blank=True, on_delete=models.PROTECT, related_name="users")` to `User`, remove `school`, and add model/manager validation that rejects a student ID on a non-staff user and rejects a staff user without one. Keep `student_id` out of `User.__str__` and API serializers.

- [ ] **Step 4: Add migration and Django Admin support**

Create one deterministic migration that creates `Institution`, adds nullable `User.institution`, converts every non-empty historic `school` value to a shared custom pending record, assigns it to the user, then removes `school`. Define label normalization inside the migration rather than importing current application code.

Register `InstitutionAdmin` with list display `label`, `source`, `review_status`, `code`, and `location`; add filters for `source` and `review_status`. Replace user-admin school fields with institution, and keep `student_id` inside its existing internal-only fieldset.

- [ ] **Step 5: Run the focused backend tests and migration checks**

Run: `uv run python manage.py makemigrations --check --dry-run`

Expected: exit 0 with `No changes detected`.

Run: `uv run python manage.py test accounts.tests.test_institutions accounts.tests.test_models -v 2`

Expected: PASS.

- [ ] **Step 6: Commit the model layer**

```bash
git add server/accounts
git commit -m "feat: add institution catalogue domain"
```

### Task 2: Import the university catalogue idempotently

**Files:**
- Create: `server/accounts/management/__init__.py`
- Create: `server/accounts/management/commands/__init__.py`
- Create: `server/accounts/management/commands/import_institutions.py`
- Modify: `server/accounts/tests/test_institutions.py`
- Modify: `server/README.md`

**Interfaces:**
- Consumes: `Institution` from Task 1 and `server/university.json`
- Produces: `uv run python manage.py import_institutions [--path path/to/file.json]`

- [ ] **Step 1: Add an import-command test using a small temporary JSON file**

```python
call_command("import_institutions", path=fixture_path)
call_command("import_institutions", path=fixture_path)

institution = Institution.objects.get(value="227")
self.assertEqual(Institution.objects.filter(value="227").count(), 1)
self.assertEqual(institution.label, "University of Science")
self.assertEqual(institution.review_status, Institution.ReviewStatus.VERIFIED)
```

Add a second case that creates a custom pending institution first and proves the import never changes its source, blank fields, or review status.

- [ ] **Step 2: Run the command test and confirm it fails**

Run: `uv run python manage.py test accounts.tests.test_institutions.InstitutionImportCommandTests -v 2`

Expected: FAIL because `import_institutions` is not registered.

- [ ] **Step 3: Implement the idempotent import command**

```python
for record in payload["data"]:
    Institution.objects.update_or_create(
        source=Institution.Source.CATALOGUE,
        value=str(record["value"]),
        defaults={
            "label": record["label"].strip(),
            "normalized_label": normalize_institution_label(record["label"]),
            "code": record.get("code", "").strip(),
            "short_name": record.get("shortName", "").strip(),
            "english_name": record.get("eng", "").strip(),
            "type": record.get("type", "").strip(),
            "location": record.get("location", "").strip(),
            "review_status": Institution.ReviewStatus.VERIFIED,
        },
    )
```

Default `--path` to `settings.BASE_DIR / "university.json"`. Reject payloads without a list in `data` using `CommandError`. Document the command directly below the migration commands in `server/README.md`.

- [ ] **Step 4: Verify import behavior**

Run: `uv run python manage.py test accounts.tests.test_institutions.InstitutionImportCommandTests -v 2`

Expected: PASS.

Run: `uv run python manage.py import_institutions`

Expected: exit 0 and a summary of created and updated catalogue records.

- [ ] **Step 5: Commit the importer**

```bash
git add server/accounts/management server/accounts/tests/test_institutions.py server/README.md
git commit -m "feat: import institution catalogue"
```

### Task 3: Expose institution search and update the account API

**Files:**
- Modify: `server/accounts/serializers.py`
- Modify: `server/accounts/views.py`
- Modify: `server/accounts/urls.py`
- Modify: `server/accounts/tests/test_api.py`

**Interfaces:**
- Consumes: `resolve_institution` and `Institution` from Task 1
- Produces: `GET /api/institutions/?q=<text>` and account inputs `institution_id` or `institution_label`
- Produces: account response `institution: { id, value, label, code, shortName, eng, type, location } | null`

- [ ] **Step 1: Write API tests for search, canonical selection, custom input, and privacy**

```python
response = self.client.get("/api/institutions/?q=science")
self.assertEqual(response.status_code, status.HTTP_200_OK)
self.assertEqual(response.data[0]["label"], "University of Science")

response = self.client.post("/api/auth/register/", {
    "email": "player@example.com", "password": "strong-password-123",
    "first_name": "Minh", "last_name": "Nguyen", "institution_label": "New Academy",
}, format="json")
self.assertEqual(response.status_code, status.HTTP_201_CREATED)
self.assertEqual(response.data["institution"]["label"], "New Academy")
self.assertNotIn("student_id", response.data)
```

Add assertions that both input fields, neither input field, a nonexistent catalogue ID, and a blank custom label return 400. Patch `/api/account/me/` with each valid input form, then assert email and `student_id` remain unchanged.

- [ ] **Step 2: Run account API tests and confirm the old contract fails**

Run: `uv run python manage.py test accounts.tests.test_api -v 2`

Expected: FAIL because serializers still accept `school` and no search route exists.

- [ ] **Step 3: Implement serializers and search view**

```python
class InstitutionSerializer(serializers.ModelSerializer):
    shortName = serializers.CharField(source="short_name")
    eng = serializers.CharField(source="english_name")

    class Meta:
        model = Institution
        fields = ("id", "value", "label", "code", "shortName", "eng", "type", "location")

class InstitutionSearchView(generics.ListAPIView):
    serializer_class = InstitutionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        return Institution.objects.filter(source=Institution.Source.CATALOGUE).filter(
            Q(label__icontains=query) | Q(code__icontains=query) |
            Q(short_name__icontains=query) | Q(english_name__icontains=query) |
            Q(location__icontains=query)
        ).order_by("label")[:20]
```

Give registration and profile serializers write-only `institution_id` and `institution_label` fields. Their shared validation calls `resolve_institution`; their read representation nests `InstitutionSerializer`. Do not expose `source`, `review_status`, `normalized_label`, or `student_id`. Add `path("institutions/", InstitutionSearchView.as_view(), name="institution-search")` to `accounts.urls`.

- [ ] **Step 4: Verify the backend contract**

Run: `uv run python manage.py test accounts.tests.test_api accounts.tests.test_institutions -v 2`

Expected: PASS.

Run: `uv run python manage.py check`

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit the API contract**

```bash
git add server/accounts/serializers.py server/accounts/views.py server/accounts/urls.py server/accounts/tests
git commit -m "feat: add institution account API"
```

### Task 4: Add the frontend institution API and accessible combobox

**Files:**
- Create: `web/src/lib/api/institutions.ts`
- Create: `web/src/lib/components/forms/InstitutionCombobox.svelte`
- Create: `web/src/lib/components/forms/institution-combobox.svelte.spec.ts`
- Modify: `web/src/lib/api/types.ts`
- Modify: `web/src/lib/api/auth.ts`

**Interfaces:**
- Consumes: `GET /api/institutions/?q=<text>` from Task 3
- Produces: `Institution`, `InstitutionChoice`, `searchInstitutions(query)`, and `<InstitutionCombobox bind:choice />`

- [ ] **Step 1: Write combobox tests for result selection and free-text fallback**

```typescript
await page.getByLabelText('Institution').fill('science');
await expect.element(page.getByRole('option', { name: /University of Science/ })).toBeVisible();
await page.getByRole('option', { name: /University of Science/ }).click();
expect(choice).toEqual({ institution_id: 7 });

await page.getByLabelText('Institution').fill('New Academy');
await page.getByRole('button', { name: /Use "New Academy"/ }).click();
expect(choice).toEqual({ institution_label: 'New Academy' });
```

Mock `searchInstitutions` in the test. Add a keyboard test for ArrowDown then Enter and an error-rendering test.

- [ ] **Step 2: Run the component test and confirm it fails**

Run: `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts`

Expected: FAIL because the component and institution API module do not exist.

- [ ] **Step 3: Add client types, requests, and component behavior**

```typescript
export interface Institution {
    id: number;
    value: string;
    label: string;
    code: string;
    shortName: string;
    eng: string;
    type: string;
    location: string;
}

export type InstitutionChoice =
    | { institution_id: number; institution_label?: never }
    | { institution_id?: never; institution_label: string };

export function searchInstitutions(query: string) {
    return requestJson<Institution[]>(`/institutions/?q=${encodeURIComponent(query)}`);
}
```

`InstitutionCombobox` debounces requests, renders listbox options with institution label and available metadata, supports ArrowDown, ArrowUp, Enter, Escape, and pointer selection, and exposes the selected/free-text `InstitutionChoice` through a bindable prop. It preserves an entered non-empty label when search returns no result, instead of forcing a selection.

- [ ] **Step 4: Verify component behavior**

Run: `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts`

Expected: PASS.

Run: `pnpm check`

Expected: the new component has no TypeScript or Svelte diagnostics; record pre-existing diagnostics separately if they remain.

- [ ] **Step 5: Commit the reusable frontend primitive**

```bash
git add web/src/lib/api web/src/lib/components/forms
git commit -m "feat: add institution search combobox"
```

### Task 5: Update account pages and detach registration from account defaults

**Files:**
- Modify: `web/src/routes/auth/register/+page.svelte`
- Modify: `web/src/routes/account/profile/+page.svelte`
- Modify: `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- Modify: `web/src/lib/components/registrations/RosterEditor.svelte`
- Modify: `web/src/routes/auth-pages.svelte.spec.ts`
- Modify: `web/src/routes/registration-pages.svelte.spec.ts`
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Interfaces:**
- Consumes: `InstitutionChoice` and `<InstitutionCombobox>` from Task 4
- Produces: account creation/profile requests with institution input only; registration roster rows with no account prefill

- [ ] **Step 1: Rewrite account-page tests around institution choices**

```typescript
vi.mocked(registerAccount).mockResolvedValue(user);
await page.getByLabelText('Institution').fill('University of Science');
await page.getByRole('option', { name: /University of Science/ }).click();
await page.getByRole('button', { name: 'Create account' }).click();

expect(registerAccount).toHaveBeenCalledWith({
    email: 'player@example.com', password: 'strong-password',
    first_name: 'Minh', last_name: 'Nguyen', institution_id: 7,
});
```

Add profile coverage for a custom institution update. Replace every `CurrentUser.school` or `CurrentUser.gamer_tag` fixture with an `institution` object.

- [ ] **Step 2: Run focused frontend tests and confirm old assumptions fail**

Run: `pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts`

Expected: FAIL because pages still submit `school` and registration reads removed account fields.

- [ ] **Step 3: Implement page changes and localized copy**

Replace the account school `<Field>` with `<InstitutionCombobox>` on both account pages. Pass `institution_id` or `institution_label` from the selected choice, retain API field-error handling, and set the profile state from `currentUser.institution`.

Remove `getCurrentUser`, `CurrentUser`, `initialGamerTag`, and `initialSchool` from the tournament registration page. Let `RosterEditor` initialize roster snapshot fields as empty text. Restore the existing roster-only `field_gamer_tag` message because gamer tags remain form data, not account data.

Add these English messages and equivalent Vietnamese translations:

```json
"field_institution": "Institution",
"institution_search_placeholder": "Type to search institutions",
"institution_no_matches": "No institutions found",
"institution_use_custom": "Use \"{label}\"",
"field_gamer_tag": "Gamer tag"
```

Change account-copy text so it describes identity and institution settings, not defaults used to prefill tournament registration.

- [ ] **Step 4: Verify the account and registration boundary**

Run: `pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts`

Expected: PASS for the updated files.

Run: `pnpm check`

Expected: no diagnostics caused by removed `CurrentUser.school` or `CurrentUser.gamer_tag` references; record unrelated RichText diagnostics separately.

- [ ] **Step 5: Commit the account UI migration**

```bash
git add web/src/routes web/src/lib/components/registrations web/messages
git commit -m "feat: use institutions in account settings"
```

### Task 6: Repair account-related backend fixtures and perform scoped verification

**Files:**
- Modify: `server/accounts/tests/test_models.py`
- Modify: `server/accounts/tests/test_api.py`
- Modify: each non-seed test file returned by `rg -l "create_user\\(" server --glob "test_*.py"`
- Modify: `server/accounts/admin.py` tests if staff creation coverage belongs in `server/accounts/tests/test_models.py`

**Interfaces:**
- Consumes: required first/last names and staff-only student ID from Task 1
- Produces: test fixtures that construct valid current users without restoring `school` or account gamer tags

- [ ] **Step 1: Add an explicit valid-user helper in account tests**

```python
def create_account(*, email="player@example.com", is_staff=False, **overrides):
    fields = {"first_name": "Minh", "last_name": "Nguyen", **overrides}
    if is_staff:
        fields["student_id"] = fields.get("student_id", "22120001")
    return get_user_model().objects.create_user(
        email=email, password="strong-password", is_staff=is_staff, **fields
    )
```

Use explicit first/last names in each existing direct `create_user` test fixture. Supply a student ID only for staff fixtures. Do not add institution fixtures where a test does not exercise public account registration.

- [ ] **Step 2: Run the affected backend tests and confirm fixture failures are gone**

Run: `uv run python manage.py test accounts config registrations tournaments -v 2`

Expected: account-manager `First name is required` and `Last name is required` errors are gone. Report deferred seed-data failures separately instead of changing the unfinished seed feature.

- [ ] **Step 3: Run static checks and focused full-stack verification**

Run: `uv run ruff check .`

Expected: `All checks passed!`

Run: `pnpm check`

Expected: no account/institution diagnostics; record any unrelated existing diagnostics.

Run: `pnpm exec vitest run src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/forms/institution-combobox.svelte.spec.ts`

Expected: PASS.

- [ ] **Step 4: Commit fixture and verification updates**

```bash
git add server/accounts/tests server/config/tests server/registrations/tests server/tournaments/tests
git commit -m "test: update account identity fixtures"
```

## Final verification checklist

- [ ] `uv run python manage.py makemigrations --check --dry-run`
- [ ] `uv run python manage.py test accounts.tests.test_institutions accounts.tests.test_api accounts.tests.test_models -v 2`
- [ ] `uv run python manage.py check`
- [ ] `uv run ruff check .`
- [ ] `pnpm exec vitest run src/lib/components/forms/institution-combobox.svelte.spec.ts src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts`
- [ ] `pnpm check`
- [ ] `git status --short --branch`

The final handoff must state which account-institution checks pass and separately list any known failures in the deferred seed feature or unrelated RichText/locale work.
