# Tournament Catalogue and Public UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task by task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 2 of the tournament portal by adding cover images and a
featured flag to tournaments, redesigning the public card grid, improving all UI
states, auditing accessibility and translations, and wiring `TournamentGame` as a
`StackedInline` inside the tournament admin page.

**Architecture:** Two ordered, independently testable commits.
*Commit A (backend)*: Pillow dependency, model fields, migration, serializer
changes, queryset ordering, admin inline.
*Commit B (frontend)*: TypeScript type update, `TournamentCard` redesign,
`TournamentCardSkeleton`, grid layout on both listing surfaces, empty state
improvement, accessibility fixes, translation additions.

**Tech Stack:** Django 6, Django REST Framework, Pillow, Python `unittest`,
SvelteKit 2, Svelte 5, TypeScript, Tailwind CSS v4, shadcn-svelte (`Skeleton`),
Paraglide, Vitest browser mode, pnpm, uv.

## Global Constraints

- `cover_image` is nullable (`null=True, blank=True`); `is_featured` defaults to
  `False`. Both are backward-compatible; no data migration is required.
- Add `Pillow>=11.0` to `server/pyproject.toml` before making migrations.
- Serialize `cover_image` as an absolute URI via
  `request.build_absolute_uri(obj.cover_image.url)` or `null` when the field is
  empty. Never serialize an empty string.
- Import `StackedInline` from `unfold.admin` (consistent with the project's
  Unfold theme). Keep the existing top-level `TournamentGameAdmin` registered.
- Replace `flex flex-col gap-4` with `grid grid-cols-1 gap-4 md:grid-cols-2
  xl:grid-cols-3` on both `/` and `/tournaments`.
- Featured cards emit `col-span-full` on their `<article>` wrapper; grid cards
  occupy one cell.
- Hide the image `<figure>` entirely when `cover_image` is `null`. No
  placeholder element, no empty space.
- Add all four new message keys to **both** `en.json` and `vi.json` before
  shipping the frontend commit.
- Keep `pnpm check` green throughout. The two new `PublicTournament` fields must
  not introduce type errors in existing callers.
- Do not modify the registration form, bracket, payment, or any other flow.

---

## Planned File Structure

| Path | Responsibility |
| --- | --- |
| `server/pyproject.toml` | Add `pillow>=11.0` to project dependencies |
| `server/tournaments/models.py` | Add `cover_image` (ImageField, nullable) and `is_featured` (BooleanField) to `Tournament` |
| `server/tournaments/migrations/000N_tournament_cover_image_featured.py` | Auto-generated migration for the two new fields |
| `server/tournaments/serializers.py` | Add `cover_image` `SerializerMethodField` and `is_featured` to `PublicTournamentSerializer` |
| `server/tournaments/views.py` | Update queryset ordering to `-is_featured, starts_at, name, pk` |
| `server/tournaments/admin.py` | Add `TournamentGameInline` (StackedInline) and update `TournamentAdmin` fields and `list_display` |
| `web/src/lib/api/types.ts` | Add `cover_image: string \| null` and `is_featured: boolean` to `PublicTournament` |
| `web/src/lib/components/tournaments/TournamentCard.svelte` | Redesign with `grid` and `featured` variants; cover image support |
| `web/src/lib/components/tournaments/TournamentCardSkeleton.svelte` | New skeleton loading placeholder matching the compact card shape |
| `web/src/routes/+page.svelte` | Replace flex stack with CSS grid; pass `variant` prop |
| `web/src/routes/tournaments/+page.svelte` | Replace flex stack with CSS grid; improve empty state |
| `web/src/lib/components/layout/AppShell.svelte` | Add `aria-current="page"` to active nav link; add `flex-wrap` to primary nav row |
| `web/messages/en.json` | Add `tournament_cover_alt`, `tournament_featured_label`, `tournament_loading`, `empty_tournaments_note` |
| `web/messages/vi.json` | Add the same four keys in Vietnamese |
| `docs/TODO-general.md` | Mark Phase 2 items complete after full verification |

---

### Task 1: Add Pillow and Run `uv sync`

**Files:**
- Modify: `server/pyproject.toml`

**Step 1: Add Pillow to dependencies**

- [ ] Open `server/pyproject.toml`.
- [ ] Add `"pillow>=11.0"` to the `[project].dependencies` list.

**Step 2: Sync the virtual environment**

```powershell
cd server
uv sync
```

- [ ] Confirm `uv sync` exits cleanly with no resolver errors.
- [ ] Confirm Pillow appears in `uv pip list`.

**Step 3: System check**

```powershell
uv run python manage.py check
```

- [ ] No errors relating to `ImageField` or Pillow. If any appear, Pillow
  did not install correctly — resolve before proceeding.

---

### Task 2: Add Model Fields and Generate Migration

**Files:**
- Modify: `server/tournaments/models.py`
- Create: migration file (auto-generated)

**Step 1: Add fields to the Tournament model**

In `server/tournaments/models.py`, inside the `Tournament` class after
`is_published`, add:

```python
cover_image = models.ImageField(
    upload_to='tournaments/covers/',
    null=True,
    blank=True,
)
is_featured = models.BooleanField(default=False)
```

- [ ] Field `cover_image` placed after `is_published`.
- [ ] Field `is_featured` placed after `cover_image`.
- [ ] No other model changes.

**Step 2: Make the migration**

```powershell
uv run python manage.py makemigrations tournaments --name tournament_cover_image_featured
```

- [ ] One new migration file created under `server/tournaments/migrations/`.
- [ ] The migration contains two `AddField` operations (cover_image,
  is_featured) and nothing else.

**Step 3: Apply and verify**

```powershell
uv run python manage.py migrate
uv run python manage.py migrate --check
uv run python manage.py check
```

- [ ] `migrate` applies cleanly.
- [ ] `migrate --check` exits 0 (no unapplied migrations).
- [ ] `check` reports no errors.

---

### Task 3: Update Serializer and Queryset Ordering

**Files:**
- Modify: `server/tournaments/serializers.py`
- Modify: `server/tournaments/views.py`

**Step 1: Update `PublicTournamentSerializer`**

At the top of `server/tournaments/serializers.py`, ensure `Tournament` is
imported:

```python
from .models import Tournament, TournamentGame
```

Inside `PublicTournamentSerializer`, add the two new fields **before**
`Meta`:

```python
cover_image = serializers.SerializerMethodField()
is_featured = serializers.BooleanField(read_only=True)

def get_cover_image(self, obj: Tournament) -> str | None:
    if not obj.cover_image:
        return None
    request = self.context.get('request')
    if request:
        return request.build_absolute_uri(obj.cover_image.url)
    return obj.cover_image.url
```

- [ ] `cover_image` SerializerMethodField declared.
- [ ] `get_cover_image` returns `None` when the field is falsy.
- [ ] `get_cover_image` builds an absolute URI when a request is present.
- [ ] `is_featured` BooleanField declared.

**Step 2: Add the new fields to `Meta.fields`**

```python
class Meta:
    model = Tournament
    fields = (
        'id',
        'name',
        'slug',
        'description',
        'starts_at',
        'ends_at',
        'location',
        'cover_image',    # new
        'is_featured',    # new
        'tournament_games',
    )
```

- [ ] Both new field names present in the tuple.

**Step 3: Update queryset ordering in `PublicTournamentViewSet`**

In `server/tournaments/views.py`, change `.order_by(...)`:

```python
.order_by('-is_featured', 'starts_at', 'name', 'pk')
```

- [ ] Ordering starts with `-is_featured`.

**Step 4: System check**

```powershell
uv run python manage.py check
```

- [ ] No errors.

---

### Task 4: Add the Admin Inline

**Files:**
- Modify: `server/tournaments/admin.py`

**Step 1: Import StackedInline**

Change the top import:

```python
from unfold.admin import ModelAdmin, StackedInline
```

- [ ] `StackedInline` imported from `unfold.admin`.

**Step 2: Define `TournamentGameInline`**

Add before `TournamentAdmin`:

```python
class TournamentGameInline(StackedInline):
    model = TournamentGame
    extra = 1
    min_num = 0
    show_change_link = True
    fields = (
        'game',
        'team_size_min',
        'team_size_max',
        'registration_opens_at',
        'registration_closes_at',
        'registration_capacity',
        'fee_amount',
        'fee_currency',
    )
```

- [ ] All seven game fields listed explicitly.
- [ ] `extra = 1` so one empty form appears by default.
- [ ] `show_change_link = True` links to the full-detail edit page.

**Step 3: Update `TournamentAdmin`**

- [ ] Add `inlines = [TournamentGameInline]` to `TournamentAdmin`.
- [ ] Add `'is_featured'` to `list_display`.
- [ ] Add `'cover_image'` and `'is_featured'` to the admin form (either via
  `fields` or by ensuring they appear in the default fieldset).

Resulting `list_display`:
```python
list_display = ('name', 'slug', 'starts_at', 'ends_at', 'is_published', 'is_featured')
```

**Step 4: Verify admin loads**

```powershell
uv run python manage.py check
```

- [ ] No errors. Start the dev server and navigate to a tournament change
  page to visually confirm the inline renders.

---

### ── COMMIT A: backend ──

At this point, all backend changes are complete. Commit:

```
Add cover_image and is_featured to Tournament; add TournamentGame inline

- Add cover_image (ImageField, nullable) and is_featured (BooleanField)
  to Tournament model with migration
- Add Pillow>=11.0 to server dependencies
- Expose cover_image (absolute URI or null) and is_featured in the
  public tournament serializer
- Order featured tournaments first in the queryset
- Add TournamentGameInline (StackedInline) to TournamentAdmin
```

---

### Task 5: Update the TypeScript Type

**Files:**
- Modify: `web/src/lib/api/types.ts`

**Step 1: Add new fields to `PublicTournament`**

```typescript
export interface PublicTournament {
  id: number;
  name: string;
  slug: string;
  description: string;
  starts_at: string | null;
  ends_at: string | null;
  location: string;
  cover_image: string | null;
  is_featured: boolean;
  tournament_games: PublicTournamentGame[];
}
```

- [ ] `cover_image: string | null` added.
- [ ] `is_featured: boolean` added.
- [ ] No other fields changed.

**Step 2: Type-check**

```powershell
cd web && pnpm check
```

- [ ] No new type errors. The new fields are not yet used in components
  (added in Task 6), so callers remain valid without changes yet.

---

### Task 6: Redesign TournamentCard

**Files:**
- Modify: `web/src/lib/components/tournaments/TournamentCard.svelte`
- Create: `web/src/lib/components/tournaments/TournamentCardSkeleton.svelte`

**Step 1: Write focused tests before redesigning**

Add component-level test assertions (in an existing or new
`TournamentCard.svelte.spec.ts`) covering:

- [ ] Grid variant: no `<figure>` or `<img>` when `cover_image` is `null`.
- [ ] Grid variant: `<img>` with `src` matching `cover_image` and `alt`
  containing the tournament name when `cover_image` is non-null.
- [ ] Featured variant: `<article>` element has the class `col-span-full`.
- [ ] `headingLevel={2}` renders `<h2>`, `headingLevel={3}` renders `<h3>`.

Run and confirm failures before editing the component:

```powershell
pnpm exec vitest run --project client src/lib/components/tournaments/
```

**Step 2: Rewrite `TournamentCard.svelte`**

Replace the component's script and markup. New Props interface:

```typescript
interface Props {
  tournament: PublicTournament;
  displayTimeZone: string;
  headingLevel?: 2 | 3;
  variant?: 'grid' | 'featured';
}

let { tournament, displayTimeZone, headingLevel = 2, variant = 'grid' }: Props = $props();
```

**Featured variant markup** (mirrors current wide layout; cover image
added as full-width header above the Card.Root):

```svelte
{#if variant === 'featured'}
<article class="col-span-full">
  {#if tournament.cover_image}
    <figure class="aspect-video overflow-hidden rounded-t-[var(--radius)]">
      <img
        class="h-full w-full object-cover"
        src={tournament.cover_image}
        alt={m.tournament_cover_alt({ name: tournament.name })}
        loading="eager"
      />
    </figure>
  {/if}
  <Card.Root class="grid gap-0 rounded-t-none py-0 md:grid-cols-[minmax(0,1fr)_17rem]">
    <!-- existing Header, Content, Footer layout unchanged -->
  </Card.Root>
</article>
```

**Grid variant markup** (compact single-column):

```svelte
{:else}
<article>
  <Card.Root class="flex flex-col gap-0 py-0">
    {#if tournament.cover_image}
      <figure class="aspect-video overflow-hidden rounded-t-[var(--radius)]">
        <img
          class="h-full w-full object-cover"
          src={tournament.cover_image}
          alt={m.tournament_cover_alt({ name: tournament.name })}
          loading="lazy"
        />
      </figure>
    {/if}
    <Card.Header class="flex-1 p-4 sm:p-5">
      <p class="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
        {m.tournament_label()}
      </p>
      <Card.Title>
        {#if headingLevel === 3}
          <h3><a href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}>{tournament.name}</a></h3>
        {:else}
          <h2><a href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}>{tournament.name}</a></h2>
        {/if}
      </Card.Title>
      {#if tournament.description}
        <Card.Description class="line-clamp-3 leading-6">
          {tournament.description}
        </Card.Description>
      {/if}
    </Card.Header>
    <Card.Content class="p-0">
      <dl class="grid grid-cols-2 gap-px bg-border text-sm">
        <!-- dates and location cells matching existing style -->
        <div class="col-span-2 bg-card p-4">
          <dt class="text-xs text-muted-foreground">{m.tournament_games()}</dt>
          <dd class="font-mono-data mt-1 font-medium">{tournament.tournament_games.length}</dd>
        </div>
      </dl>
    </Card.Content>
    <Card.Footer class="justify-between gap-4 border-t px-4 py-4">
      <a
        class="group/action flex items-center gap-4 text-sm font-semibold text-primary"
        href={resolve(localizeInternalHref(`/tournaments/${tournament.slug}`))}
      >
        {m.action_view_tournament()}
        <span class="bracket-node" aria-hidden="true"></span>
      </a>
    </Card.Footer>
  </Card.Root>
</article>
{/if}
```

- [ ] `variant` prop defaults to `'grid'`.
- [ ] `cover_image` renders in featured variant with `loading="eager"`.
- [ ] `cover_image` renders in grid variant with `loading="lazy"`.
- [ ] No `<figure>` when `cover_image` is null in either variant.
- [ ] `col-span-full` on featured `<article>`.
- [ ] All existing date, location, and game-count cells preserved in both
  variants.

**Step 3: Create `TournamentCardSkeleton.svelte`**

```svelte
<script lang="ts">
  import { Skeleton } from '$lib/components/ui/skeleton';
</script>

<div class="rounded-[var(--radius)] border border-border" aria-hidden="true">
  <Skeleton class="aspect-video w-full rounded-t-[var(--radius)] rounded-b-none" />
  <div class="flex flex-col gap-3 p-4">
    <Skeleton class="h-3 w-1/4" />
    <Skeleton class="h-5 w-3/4" />
    <Skeleton class="h-4 w-full" />
    <Skeleton class="h-4 w-2/3" />
    <div class="mt-1 grid grid-cols-2 gap-2">
      <Skeleton class="h-4" />
      <Skeleton class="h-4" />
    </div>
  </div>
</div>
```

- [ ] File created at
  `web/src/lib/components/tournaments/TournamentCardSkeleton.svelte`.
- [ ] Uses the existing `Skeleton` component from
  `$lib/components/ui/skeleton`.
- [ ] `aria-hidden="true"` on the wrapper (decorative loading state).

**Step 4: Run focused tests and confirm green**

```powershell
pnpm exec vitest run --project client src/lib/components/tournaments/
```

- [ ] All tests pass including the four new assertions from Step 1.

---

### Task 7: Replace Grid Layout on Listing Pages

**Files:**
- Modify: `web/src/routes/+page.svelte`
- Modify: `web/src/routes/tournaments/+page.svelte`

**Step 1: Import `TournamentCardSkeleton` in both files**

Add at the top of each `<script>` block:

```typescript
import TournamentCardSkeleton from '$lib/components/tournaments/TournamentCardSkeleton.svelte';
```

(The skeleton is imported here for future use during client navigation;
it is not conditionally rendered in the initial SSR since `load()` resolves
before the page renders.)

**Step 2: Update home page (`web/src/routes/+page.svelte`)**

Replace:
```svelte
<div class="flex flex-col gap-4">
  {#each data.tournaments as tournament (tournament.id)}
    <TournamentCard {tournament} displayTimeZone={data.displayTimeZone} headingLevel={3} />
  {/each}
</div>
```

With:
```svelte
<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
  {#each data.tournaments as tournament (tournament.id)}
    <TournamentCard
      {tournament}
      displayTimeZone={data.displayTimeZone}
      headingLevel={3}
      variant={tournament.is_featured ? 'featured' : 'grid'}
    />
  {/each}
</div>
```

- [ ] `flex flex-col gap-4` replaced with `grid grid-cols-1 gap-4
  md:grid-cols-2 xl:grid-cols-3`.
- [ ] `variant` prop passed to each card.

**Step 3: Update `/tournaments` listing (`web/src/routes/tournaments/+page.svelte`)**

Replace the section containing the card list:

```svelte
{#if data.tournaments.length > 0}
  <section class="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label={m.published_tournaments_heading()}>
    {#each data.tournaments as tournament (tournament.id)}
      <TournamentCard
        {tournament}
        displayTimeZone={data.displayTimeZone}
        variant={tournament.is_featured ? 'featured' : 'grid'}
      />
    {/each}
  </section>
{:else}
  <div
    class="mt-8 border border-(--line) bg-(--surface-muted) p-8 text-center"
    role="status"
  >
    <p class="text-sm font-medium text-(--text-muted)">{m.empty_tournaments()}</p>
    <p class="mt-2 text-xs text-(--text-muted)">{m.empty_tournaments_note()}</p>
  </div>
{/if}
```

- [ ] `section` element uses the grid classes.
- [ ] `variant` prop passed to each card (no `headingLevel` needed here;
  default `headingLevel={2}` is correct).
- [ ] Empty state uses the new `empty_tournaments_note` message key.

**Step 4: Type-check**

```powershell
pnpm check
```

- [ ] No type errors.

---

### Task 8: Accessibility and Navigation Audit

**Files:**
- Modify: `web/src/lib/components/layout/AppShell.svelte`

**Step 1: Add `aria-current="page"` to the Tournaments nav link**

`page` from `$app/state` is already imported in `AppShell.svelte`. Find the
Tournaments `<a>` element and add the attribute:

Paraglide prefixes locale routes (`/en/...`, `/vi/...`), so check with
`.includes('/tournaments')` which covers all locale prefixes:

```svelte
<a
  class="flex min-w-(--nav-cell-min) flex-1 items-center justify-center px-4 py-2 text-center text-lg font-medium"
  style:--nav-cell-min="9rem"
  href={resolve(localizeInternalHref('/tournaments'))}
  aria-current={page.url.pathname.includes('/tournaments') ? 'page' : undefined}
>
  {m.nav_tournaments()}
</a>
```

- [ ] `aria-current="page"` attribute present when on the tournaments route.
- [ ] Attribute is `undefined` (omitted) on other routes.

**Step 2: Add `flex-wrap` to the primary nav link row**

Find the nav inner `<div>` that wraps the Tournaments and Rules links:

```svelte
<div class="flex min-h-11 flex-wrap border-(--line)">
```

- [ ] `flex-wrap` added to prevent horizontal overflow on narrow viewports.

**Step 3: Type-check and run AppShell tests**

```powershell
pnpm check
pnpm exec vitest run --project client src/lib/components/layout/
```

- [ ] No type errors.
- [ ] Existing AppShell tests still pass.

---

### Task 9: Add Translation Keys

**Files:**
- Modify: `web/messages/en.json`
- Modify: `web/messages/vi.json`

**Step 1: Add keys to `en.json`**

Add the following four keys (placement after `empty_tournaments` is
logical):

```json
"empty_tournaments_note": "Check back later for upcoming tournaments.",
"tournament_cover_alt": "Cover image for {name}",
"tournament_featured_label": "Featured",
"tournament_loading": "Loading tournaments…"
```

- [ ] All four keys present in `en.json`.

**Step 2: Add keys to `vi.json`**

```json
"empty_tournaments_note": "Hãy quay lại sau để xem các giải đấu sắp tới.",
"tournament_cover_alt": "Ảnh bìa cho {name}",
"tournament_featured_label": "Nổi bật",
"tournament_loading": "Đang tải giải đấu…"
```

- [ ] All four keys present in `vi.json`.

**Step 3: Regenerate Paraglide types**

```powershell
pnpm check
```

Paraglide regenerates message types as part of the SvelteKit build process.
`pnpm check` drives this.

- [ ] No missing-message-key errors in `pnpm check` output.
- [ ] `m.tournament_cover_alt`, `m.tournament_featured_label`,
  `m.tournament_loading`, and `m.empty_tournaments_note` are usable in
  components without type errors.

---

### Task 10: Final Verification

**Step 1: Backend full check**

```powershell
cd server
uv run python manage.py check
uv run python manage.py migrate --check
```

- [ ] `check` exits with no errors.
- [ ] `migrate --check` exits 0 (no unapplied migrations).

**Step 2: Frontend full check and test suite**

```powershell
cd web
pnpm check
pnpm exec vitest run --project client
```

- [ ] `pnpm check` green (note any pre-existing RichText type baseline
  errors if unchanged).
- [ ] All Vitest client tests pass.

**Step 3: Manual smoke test**

Start both the Django dev server and the SvelteKit dev server. Then:

- [ ] Upload a cover image to a tournament via the Django admin.
- [ ] Set `is_featured = True` on that tournament.
- [ ] Visit the home page and `/tournaments`; confirm:
  - Featured card spans full grid width with the cover image.
  - Non-featured cards occupy individual grid cells.
  - Non-featured cards without a cover image show no empty image slot.
- [ ] Visit `/tournaments` with no browser JavaScript to confirm the grid
  renders correctly in SSR.
- [ ] Confirm `aria-current="page"` on the Tournaments nav link via browser
  dev tools when on `/tournaments`.
- [ ] Add a game division directly inside a tournament via the admin inline
  and confirm it saves successfully.

**Step 4: Update `docs/TODO-general.md`**

Mark all Phase 2 items as complete:

```markdown
## 2. Tournament catalogue and public UI

- [x] Replace full-width desktop tournament listings with a responsive card grid.
- [x] Keep the wide presentation as an optional featured-tournament treatment.
- [x] Add an image-ready tournament card contract, cover support, and fallback state.
- [x] Improve empty, loading, closed, upcoming, and full-registration states.
- [x] Audit navigation, tournament detail pages, mobile layout, accessibility, and translations.
- [x] Let admins add and edit divisions (TournamentGame) directly inside a tournament.
```

- [ ] All six items marked complete.

---

### ── COMMIT B: frontend ──

```
Tournament catalogue: responsive card grid, cover images, featured treatment

- Add cover_image and is_featured to PublicTournament TypeScript type
- Redesign TournamentCard with grid and featured variants; cover image
  renders when present, suppressed entirely when null
- Add TournamentCardSkeleton component for client navigation loading
- Replace flex stack with 1/2/3 column responsive grid on home and
  /tournaments pages; featured cards span full row
- Improve empty state with note message
- Add aria-current="page" to active Tournaments nav link
- Add flex-wrap to primary nav row for mobile overflow safety
- Add tournament_cover_alt, tournament_featured_label, tournament_loading,
  and empty_tournaments_note to en.json and vi.json
```

---

## Final Handoff Checklist

- [ ] `server/pyproject.toml` includes `pillow>=11.0`.
- [ ] `Tournament.cover_image` is an `ImageField(upload_to='tournaments/covers/', null=True, blank=True)`.
- [ ] `Tournament.is_featured` is a `BooleanField(default=False)`.
- [ ] Migration applies cleanly; `manage.py migrate --check` exits 0.
- [ ] `manage.py check` passes with no errors.
- [ ] `PublicTournamentSerializer` exposes `cover_image` as absolute URI or `null`.
- [ ] `PublicTournamentSerializer` exposes `is_featured` as boolean.
- [ ] Queryset ordered by `-is_featured, starts_at, name, pk`.
- [ ] `TournamentGameInline` (StackedInline) wired into `TournamentAdmin`.
- [ ] Existing top-level `TournamentGameAdmin` still registered.
- [ ] `PublicTournament` TypeScript type includes `cover_image: string | null` and `is_featured: boolean`.
- [ ] `TournamentCard` grid variant hides `<figure>` when `cover_image` is `null`.
- [ ] `TournamentCard` grid variant renders `<img>` with correct `src` and `alt` when `cover_image` is non-null.
- [ ] `TournamentCard` featured variant article has class `col-span-full`.
- [ ] `TournamentCardSkeleton` component created and importable.
- [ ] Home page and `/tournaments` use `grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3`.
- [ ] `variant` prop passed as `tournament.is_featured ? 'featured' : 'grid'` at both call sites.
- [ ] Empty state on `/tournaments` uses the styled panel with `empty_tournaments_note`.
- [ ] `aria-current="page"` present on the Tournaments nav link when on the tournaments route.
- [ ] Primary nav row has `flex-wrap`.
- [ ] `tournament_cover_alt`, `tournament_featured_label`, `tournament_loading`, `empty_tournaments_note` present in both `en.json` and `vi.json`.
- [ ] `pnpm check` green.
- [ ] `pnpm exec vitest run --project client` green.
- [ ] `docs/TODO-general.md` Phase 2 items all marked complete.
