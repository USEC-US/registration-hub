# Tournament Catalogue and Public UI Design

## Purpose

Phase 2 makes the tournament catalogue visually complete and operationally
manageable. This phase adds a cover image and featured flag to tournaments,
redesigns the public listing into a responsive card grid, improves all
tournament UI states (empty, loading, closed, full, upcoming), audits
accessibility and translations, and lets organizers manage game divisions
directly inside a tournament record in the Django admin.

## Goals

- Add `cover_image` (ImageField, nullable) and `is_featured` (BooleanField)
  to the `Tournament` model with a backward-compatible migration.
- Add `Pillow` to the server dependency set to satisfy `ImageField` image
  validation.
- Expose `cover_image` as an absolute URI (or null) and `is_featured` as a
  boolean in the public tournament API.
- Order the public queryset to surface featured tournaments first, then
  chronologically.
- Add a `TournamentGameInline` (StackedInline) to `TournamentAdmin` so
  organizers can add, edit, and remove game divisions without leaving the
  tournament page.
- Replace the full-width `flex flex-col gap-4` stack of tournament cards on
  both the home page and `/tournaments` with a responsive CSS grid:
  1 column on mobile, 2 columns at `md`, 3 columns at `xl`.
- Render featured tournaments spanning the full grid width (`col-span-full`).
- Render a cover image at the top of each card when available; suppress the
  image slot entirely when `cover_image` is null — no placeholder, no empty
  space.
- Update the TypeScript `PublicTournament` interface to include the two new
  fields.
- Redesign `TournamentCard` to support a compact grid variant and a featured
  wide variant, driven by the `is_featured` flag from the API.
- Add a `TournamentCardSkeleton` component for client-side navigation loading
  states.
- Improve the empty-state presentation on both the listing and home page
  section.
- Audit and fix: active nav link indication, mobile nav overflow, cover image
  alt text, and missing translation keys in both locale files.

## Non-goals

- Building a standalone organizer frontend beyond the Django admin inline.
- Image resizing, thumbnail generation, CDN optimization, or lazy-load
  strategies for production media hosting.
- Image cropping or upload preview in the admin.
- Tournament search, filtering, or sorting controls in the public UI.
- Changes to the registration form, bracket, or payment flows.
- Making registration windows or capacity editable from the public UI.
- Full dark-mode cover image fallbacks or branded placeholder illustrations.

## Current Surface

| Layer | Current state |
| --- | --- |
| `Tournament` model | `name`, `slug`, `description`, `starts_at`, `ends_at`, `location`, `is_published` |
| `TournamentGame` admin | Top-level `ModelAdmin` only; no inline on `TournamentAdmin` |
| `PublicTournamentSerializer` | `id`, `name`, `slug`, `description`, `starts_at`, `ends_at`, `location`, `tournament_games` |
| Queryset ordering | `starts_at`, `name`, `pk` |
| `/tournaments` listing | `flex flex-col gap-4` stack; plain `<p role="status">` empty state |
| Home page section | Same stack inside a section; `headingLevel={3}` |
| `TournamentCard` | 2-column grid on `md` (content + 17 rem sidebar); no image support |
| `TournamentGameRow` | Registration state via Badge; no cover, no upcoming-opens detail |
| `PublicTournament` TypeScript type | No `cover_image`, no `is_featured` |
| `Pillow` | Not in `server/pyproject.toml` |
| `MEDIA_URL` / `MEDIA_ROOT` | Already configured; DEBUG media serving already wired in `config/urls.py` |

## Design

### Backend: Model Changes

Add two fields to the `Tournament` class in `server/tournaments/models.py`:

```python
cover_image = models.ImageField(
    upload_to='tournaments/covers/',
    null=True,
    blank=True,
)
is_featured = models.BooleanField(default=False)
```

`null=True, blank=True` on `cover_image` makes the column nullable,
cleanly distinguishing "no image uploaded" (database `NULL`) from an
empty-string path. The serializer and frontend treat `None` as the
absent-image signal.

`is_featured` defaults to `False`, so all existing tournaments remain
non-featured without a data migration.

Both fields have safe defaults. No required data migration is needed
beyond the schema migration that adds the columns.

Add `"pillow>=11.0"` to `[project].dependencies` in `server/pyproject.toml`.
Django's `ImageField` calls Pillow's image validation on upload; without it
`manage.py check` raises `ERRORS: tournaments.Tournament.cover_image:
ImageField requires Pillow`.

### Backend: Queryset Ordering

Update `PublicTournamentViewSet.get_queryset()` ordering from
`('starts_at', 'name', 'pk')` to:

```python
.order_by('-is_featured', 'starts_at', 'name', 'pk')
```

Featured tournaments sort first within the published list. Within each
group, ordering remains chronological then alphabetical.

### Backend: Serializer

Add to `PublicTournamentSerializer` in `server/tournaments/serializers.py`:

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

Add `'cover_image'` and `'is_featured'` to `Meta.fields`.

`SerializerMethodField` for `cover_image` handles the nullable case safely:
accessing `.url` on an empty `ImageField` raises `ValueError`, which this
method avoids by checking truthiness first. `is_featured` is a plain
`BooleanField` that DRF serializes without a method field.

`PublicTournamentViewSet` inherits DRF's default `get_serializer_context()`
which includes `{'request': request, ...}`, so `self.context.get('request')`
is always populated in live requests. The fallback to `obj.cover_image.url`
handles test contexts where no request object is injected.

### Backend: Admin Inline

Add a `TournamentGameInline` to `server/tournaments/admin.py`:

```python
from unfold.admin import ModelAdmin, StackedInline

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

Import `StackedInline` from `unfold.admin` (consistent with the existing
`ModelAdmin` import and the project's Unfold theme). Wire the inline into
`TournamentAdmin`:

```python
@admin.register(Tournament)
class TournamentAdmin(OrganizerStaffAdmin):
    inlines = [TournamentGameInline]
    list_display = ('name', 'slug', 'starts_at', 'ends_at', 'is_published', 'is_featured')
    ...
```

Add `cover_image` and `is_featured` to the `TournamentAdmin` form so admins
can upload images and toggle featured status from the tournament change page.

The existing top-level `TournamentGameAdmin` remains registered for global
list, search, and date-hierarchy navigation. The inline is additive.

### Frontend: Type Contract

Update `PublicTournament` in `web/src/lib/api/types.ts`:

```typescript
export interface PublicTournament {
  id: number;
  name: string;
  slug: string;
  description: string;
  starts_at: string | null;
  ends_at: string | null;
  location: string;
  cover_image: string | null;   // absolute URI or null
  is_featured: boolean;
  tournament_games: PublicTournamentGame[];
}
```

### Frontend: TournamentCard Redesign

`TournamentCard.svelte` gains a `variant: 'grid' | 'featured'` prop
(defaulting to `'grid'`). Callers pass `variant="featured"` when
`tournament.is_featured` is true. The `is_featured` flag from the API
drives which variant each caller uses; callers do not decide independently.

**Grid variant (compact):**

- The `<article>` wrapper carries no extra class (takes one grid cell).
- Cover image: when `tournament.cover_image` is non-null, render an `<img>`
  inside `<figure class="aspect-video overflow-hidden rounded-t-[var(--radius)]">`.
  Use `loading="lazy"` since compact cards may be below the fold.
  When `cover_image` is null, skip the `<figure>` entirely — no empty space.
- Card layout: single-column stack (`flex flex-col`).
- Header: kicker label → linked name (h2 or h3) → description clamped to
  3 lines via `line-clamp-3`.
- Content: compact `<dl>` row for dates and location. Game count shown as
  a small data point.
- Footer: "View tournament →" link.

**Featured variant (wide):**

- The `<article>` wrapper adds `class="col-span-full"` so the card spans
  all columns regardless of current breakpoint.
- Cover image: when present, renders as a full-width `<figure>` above the
  card body. Aspect ratio `aspect-video`, `object-cover`, `loading="eager"`
  since the featured card is typically above the fold.
- Card layout: retains the existing two-column
  `md:grid-cols-[minmax(0,1fr)_17rem]` wide layout for the metadata panel.
- All existing content (header, metadata dl, footer link) remains unchanged.

### Frontend: TournamentCardSkeleton

`TournamentCardSkeleton.svelte` renders a loading placeholder matching the
compact card shape using the existing shadcn `Skeleton` component:

```svelte
<div class="rounded-[var(--radius)] border border-border">
  <Skeleton class="aspect-video w-full rounded-t-[var(--radius)]" />
  <div class="flex flex-col gap-2 p-4">
    <Skeleton class="h-4 w-1/4" />
    <Skeleton class="h-5 w-3/4" />
    <Skeleton class="h-4 w-full" />
    <Skeleton class="h-4 w-2/3" />
  </div>
</div>
```

Three skeletons are rendered as grid children during client-side loading.

### Frontend: Grid Layout

Replace `flex flex-col gap-4` on both listing surfaces with:

```html
<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
  {#each data.tournaments as tournament (tournament.id)}
    <TournamentCard
      {tournament}
      displayTimeZone={data.displayTimeZone}
      headingLevel={...}
      variant={tournament.is_featured ? 'featured' : 'grid'}
    />
  {/each}
</div>
```

Featured cards add `col-span-full` internally, spanning the full row.
Non-featured cards occupy one cell each. The grid degrades naturally to a
single column on mobile.

### Frontend: Empty State

Replace the plain `<p role="status">` empty state with a styled panel:

```svelte
<div class="border border-(--line) bg-(--surface-muted) p-8 text-center" role="status">
  <p class="text-sm font-medium text-(--text-muted)">{m.empty_tournaments()}</p>
  <p class="mt-2 text-xs text-(--text-muted)">{m.empty_tournaments_note()}</p>
</div>
```

### Frontend: Accessibility and Navigation Audit

**Active nav link:**

Add `aria-current="page"` to the Tournaments nav link when the current
pathname matches `/tournaments`. Use `page.url.pathname` from `$app/state`
(already imported in `AppShell.svelte`):

```svelte
aria-current={page.url.pathname.startsWith('/tournaments') ? 'page' : undefined}
```

**Mobile nav overflow:**

Add `flex-wrap` to the primary nav link row to prevent text overflow on
very narrow screens (< 360 px):

```svelte
<div class="flex min-h-11 flex-wrap border-(--line)">
```

**Cover image alt text:**

Use a translated message key so alt text is localized:

```svelte
alt={m.tournament_cover_alt({ name: tournament.name })}
```

**The "Rules" disabled nav item** already has `aria-disabled="true"` on a
`<span>`. Since `<span>` is not focusable by default, it cannot confuse
keyboard-only users navigating the tab ring. No change is needed.

### New Translation Keys

The following keys must be present in both `web/messages/en.json` and
`web/messages/vi.json`:

| Key | English | Vietnamese |
| --- | --- | --- |
| `tournament_cover_alt` | `"Cover image for {name}"` | `"Ảnh bìa cho {name}"` |
| `tournament_featured_label` | `"Featured"` | `"Nổi bật"` |
| `tournament_loading` | `"Loading tournaments…"` | `"Đang tải giải đấu…"` |
| `empty_tournaments_note` | `"Check back later for upcoming tournaments."` | `"Hãy quay lại sau để xem các giải đấu sắp tới."` |
| `empty_tournaments_note` | `"Check back later for upcoming tournaments."` | `"Hãy quay lại sau để xem các giải đấu sắp tới."` |

## Testing Strategy

**Backend:**

- `cover_image` serializes to an absolute URI when an image is uploaded and
  to `null` when the field is empty.
- `is_featured` serializes to `true` and `false` correctly.
- Featured tournaments appear first in the list API response (`-is_featured`
  ordering).
- `TournamentGameInline` appears on the tournament admin change page.
- `manage.py check` passes with Pillow installed.
- Migration applies cleanly; `migrate --check` passes after the migration.

**Frontend:**

- Grid variant: no `<figure>` rendered when `cover_image` is `null`.
- Grid variant: `<img>` with correct `src` and `alt` when `cover_image` is
  a non-null string.
- Featured variant: `<article>` root element has `col-span-full`.
- `headingLevel` 2 and 3 props render `<h2>` and `<h3>` respectively.
- `aria-current="page"` is present on the Tournaments nav link when pathname
  starts with `/tournaments`.
- All four new message keys exist in both locale files.
- `pnpm check` reports no new type errors.

**Verification commands:**

```powershell
# Backend
uv run python manage.py check
uv run python manage.py migrate --check

# Frontend
pnpm check
pnpm exec vitest run --project client src/lib/components/tournaments/
pnpm exec vitest run --project client src/lib/components/layout/
```
