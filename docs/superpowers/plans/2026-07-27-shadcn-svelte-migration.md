# shadcn-svelte UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task by task.

**Goal:** Replace the application's repeated handcrafted form, feedback, card, status, and loading primitives with locally generated shadcn-svelte components while preserving the USEC visual system and all existing client behavior.

**Architecture:** Keep the generated shadcn-svelte source under `$lib/components/ui` as local, reviewable code. Retain `Field.svelte` and `ErrorSummary.svelte` as thin application adapters so their current callers and accessibility contracts remain stable. Use shadcn primitives within feature components, but keep tournament-specific structure, the grid-board/bracket motifs, and the bespoke application shell.

**Tech Stack:** Svelte 5, SvelteKit, TypeScript, Tailwind CSS v4, shadcn-svelte, Bits UI, Paraglide, Vitest Browser Mode, Playwright.

## Global Constraints

- Preserve the design tokens, fonts, light/dark definitions, focus treatment, and reduced-motion rules in `web/src/routes/layout.css`. Generated shadcn components must consume those semantic tokens; do not replace the USEC palette with a stock theme.
- Keep API calls, route shapes, session/redirect behavior, locale behavior, and Paraglide message keys unchanged. This is a UI migration, not a product-behavior change.
- Preserve the existing public contracts of `web/src/lib/components/forms/Field.svelte`: bindable `value`, label/control association, hint/error IDs, validation attributes, and `aria-describedby`/`aria-invalid` behavior. Preserve the empty-render behavior and alert semantics of `ErrorSummary.svelte`.
- Do not modify, stage, reformat, or commit the user-owned changes in `web/src/lib/components/layout/AppShell.svelte` or `web/src/lib/components/layout/AppShell.svelte.spec.ts`. Do not touch `.idea/` or the existing untracked identity/navigation plans.
- Use generated shadcn-svelte source rather than reimplementing primitives. Before generating or composing each primitive, consult its current official documentation: [Field](https://shadcn-svelte.com/docs/components/field), [Alert](https://shadcn-svelte.com/docs/components/alert), [Card](https://shadcn-svelte.com/docs/components/card), [Badge](https://shadcn-svelte.com/docs/components/badge), [Radio Group](https://shadcn-svelte.com/docs/components/radio-group), [Separator](https://shadcn-svelte.com/docs/components/separator), [Skeleton](https://shadcn-svelte.com/docs/components/skeleton), and [Spinner](https://shadcn-svelte.com/docs/components/spinner).
- Use `Field.Field` + `Field.Label` + `Input` for controls, add `data-invalid` only when an error is present, set `aria-invalid` on invalid controls, and put `Field.Error` immediately after the control. Use the existing default-export `Button` from `$lib/components/ui/button/button.svelte` plus `Spinner` for submitting states; explicitly set `type="submit"`, mark the decorative spinner `aria-hidden="true"`, and do not reproduce button or spinner CSS locally.
- Use component `class` props only for product layout and the existing tournament-specific motifs. Prefer shadcn variants and semantic tokens (`primary`, `muted`, `border`, `destructive`, `card`) over new literal colors or duplicated control styles.

## Task 1: Establish the local primitive inventory without changing product layout

**Files:**

- Create: generated directories under `web/src/lib/components/ui/alert/`, `badge/`, `card/`, `field/`, `input/`, `radio-group/`, `separator/`, `skeleton/`, and `spinner/`
- Inspect only: `web/components.json`, `web/src/routes/layout.css`, existing `web/src/lib/components/ui/button/button.svelte` and `dropdown-menu/`

**Step 1: Capture the protected worktree boundary**

Confirm the user-owned AppShell diff exists before the migration and record its file list. Do not use a broad staging command later.

```powershell
git status --short
git diff -- web/src/lib/components/layout/AppShell.svelte web/src/lib/components/layout/AppShell.svelte.spec.ts
```

**Step 2: Read the official component docs and generate only the needed source**

The project already has the default-export `Button` source at `ui/button/button.svelte`, `DropdownMenu`, `bits-ui`, `@lucide/svelte`, `tailwind-variants`, and a valid `web/components.json`; retain those sources. Generate the components that have immediate migration targets:

```powershell
pnpm dlx shadcn-svelte@latest add alert badge card field input radio-group separator skeleton spinner
```

The migration intentionally does **not** add unused `Select`, `Textarea`, or `Checkbox` source: no current product form uses those controls, and the native locale select is part of the protected AppShell work. Add them only in a later feature that needs them.

**Step 3: Verify generation uses the existing design system**

Inspect the generated imports and confirm they resolve through `$lib/utils` and the semantic Tailwind tokens already exposed by `layout.css`. Keep any CLI-created dependency/configuration change only when required by the generated components. Do not alter the root color variables, font variables, or `components.json` style selection.

```powershell
pnpm check
git diff -- web/components.json web/package.json web/pnpm-lock.yaml web/src/routes/layout.css web/src/lib/components/ui
```

Expected: all new reusable source lives in `$lib/components/ui`; no AppShell files or product routes change in this task. Record the pre-existing RichText message-typing errors if `pnpm check` reports the same six known errors.

## Task 2: Rebuild the shared field and error adapters on shadcn-svelte

**Files:**

- Modify: `web/src/lib/components/forms/Field.svelte`
- Modify: `web/src/lib/components/forms/ErrorSummary.svelte`
- Modify: `web/src/lib/components/forms/field-auth.svelte.spec.ts`
- Modify: `web/src/lib/components/design-system.svelte.spec.ts`

**Step 1: Extend the focused tests before the implementation**

Keep the present tests for label association, browser attributes, hint/error IDs, `aria-describedby`, and `aria-invalid`. Add assertions that an invalid field exposes the shadcn field error path and that a non-empty error summary renders one destructive alert containing the localized heading and all error list items. Keep the existing assertion that `ErrorSummary` renders no wrapper for `errors: []`.

Run the focused tests and confirm the newly added component-composition assertions fail before changing the adapters:

```powershell
pnpm exec vitest run --project client src/lib/components/forms/field-auth.svelte.spec.ts src/lib/components/design-system.svelte.spec.ts
```

**Step 2: Migrate `Field.svelte` without changing its caller API**

Replace the handmade `<div>`, `<label>`, and `<input>` styling with this composition while retaining every existing prop and the `$bindable` `value` contract:

```svelte
<Field.Field data-invalid={error ? true : undefined}>
  <Field.Label for={name}>{label}</Field.Label>
  <Input
    id={name}
    {name}
    {type}
    {autocomplete}
    {spellcheck}
    {required}
    {minlength}
    {maxlength}
    bind:value
    aria-describedby={describedBy}
    aria-invalid={error ? 'true' : undefined}
  />
  {#if hint}<Field.Description id={hintId}>{hint}</Field.Description>{/if}
  {#if error}<Field.Error id={errorId}>{error}</Field.Error>{/if}
</Field.Field>
```

Use the generated component's import style (`import * as Field ...` and `import { Input } ...`). Preserve the current deterministic `${name}-hint` and `${name}-error` IDs, rather than accepting generated IDs, because callers and tests already rely on them.

**Step 3: Migrate `ErrorSummary.svelte` to Alert**

Render nothing when there are no errors. Otherwise use `Alert.Root variant="destructive" role="alert"`, `Alert.Title`, and `Alert.Description` containing the existing ordered error list structure. Keep the localized title and every supplied error message; use the component's semantic destructive styling rather than the custom left border styling.

**Step 4: Verify the adapter slice**

```powershell
pnpm exec vitest run --project client src/lib/components/forms/field-auth.svelte.spec.ts src/lib/components/design-system.svelte.spec.ts
pnpm check
```

Expected: all adapter accessibility behavior remains intact and the only `pnpm check` errors are the unchanged RichText baseline, if present.

## Task 3: Migrate account, authentication, registration, payment, and roster controls

**Files:**

- Modify: `web/src/routes/auth/sign-in/+page.svelte`
- Modify: `web/src/routes/auth/register/+page.svelte`
- Modify: `web/src/routes/account/profile/+page.svelte`
- Modify: `web/src/routes/tournaments/[slug]/games/[gameId]/register/+page.svelte`
- Modify: `web/src/lib/components/registrations/PaymentAttemptForm.svelte`
- Modify: `web/src/lib/components/registrations/RosterEditor.svelte`
- Modify: `web/src/routes/auth-pages.svelte.spec.ts`
- Modify: `web/src/routes/registration-pages.svelte.spec.ts`
- Modify: `web/src/lib/components/registrations/registration-flow.svelte.spec.ts`

**Step 1: Write behavior-preserving UI tests first**

Add focused assertions alongside the current submission tests that:

- sign-in, registration, and profile submit controls are shadcn buttons and show a disabled spinner while an in-flight request is pending;
- the payment form retains its exact `FormData` names (`amount`, `currency`, `proof_file`, and `reference`), accepts either evidence path, and keeps its authentication-error callback behavior;
- roster gamer-tag and school controls remain required and bound to the same `members` array; selecting a captain still leaves exactly one selected member;
- field-level registration/team errors still reach the associated field and non-field errors still reach `ErrorSummary`.

Run these tests before implementation and confirm any new composition checks fail:

```powershell
pnpm exec vitest run --project client src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts
```

**Step 2: Convert forms to Field/Card/Button composition**

- Preserve each route's existing `onsubmit`, reactive state, API calls, redirects, localized copy, and error mapping.
- Use `Card.Root`, `Card.Header`, `Card.Title`, `Card.Description`, `Card.Content`, and `Card.Footer` for standalone auth, profile, registration, and payment surfaces. Pass small layout-only classes where the existing tournament grid requires them; do not flatten its headings, sections, or semantic form structure.
- Continue using the `Field.svelte` adapter for simple string fields. In `PaymentAttemptForm.svelte` and `RosterEditor.svelte`, compose generated `Field.Field`, `Field.Label`, and `Input` directly for file/amount/currency/reference and per-member controls so their input names and bindings remain exact.
- Replace raw submit buttons with the existing `Button` (`import Button from '$lib/components/ui/button/button.svelte'`) and explicitly pass `type="submit"`. When `submitting` is true, keep the button disabled and render `<Spinner aria-hidden="true" />` beside the existing localized label. Preserve the visible 44px target with the minimal layout class only where the project needs it.
- Replace the roster's raw radio inputs with `RadioGroup.Root`/`RadioGroup.Item`, driven by a derived selected member index/value and the existing `selectCaptain` helper. Keep the current per-member accessible name (`Set member N as captain`), only-one-captain invariant, and member display order.
- Use `Separator` for section boundaries that are semantically just dividers; keep existing structural borders when they form part of the tournament roster grid.

**Step 3: Verify form behavior and static types**

```powershell
pnpm exec vitest run --project client src/routes/auth-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts src/lib/components/registrations/registration-flow.svelte.spec.ts
pnpm check
```

Expected: all submission, validation, redirect, FormData, and roster tests pass with no new static errors.

## Task 4: Migrate tournament and registration display surfaces

**Files:**

- Modify: `web/src/lib/components/tournaments/TournamentCard.svelte`
- Modify: `web/src/lib/components/tournaments/TournamentGameRow.svelte`
- Modify: `web/src/lib/components/registrations/StatusTimeline.svelte`
- Modify: `web/src/routes/+page.svelte`
- Modify: `web/src/routes/tournaments/+page.svelte`
- Modify: `web/src/routes/tournaments/[slug]/+page.svelte`
- Modify: `web/src/routes/account/registrations/+page.svelte`
- Modify: `web/src/routes/account/registrations/[id]/+page.svelte`
- Modify: `web/src/lib/components/design-system.svelte.spec.ts`
- Modify: `web/src/routes/public-pages.svelte.spec.ts`
- Modify: `web/src/routes/public-registration.e2e.ts`

**Step 1: Add focused visual-structure tests**

Extend the existing browser tests to verify:

- tournament cards and game rows retain localized tournament/game content and their localized hrefs while exposing Card structure;
- registration and game state labels remain localized and use the appropriate Badge semantics/variants;
- the registration status timeline remains an ordered list with its current `aria-current="step"` and machine-readable `<time>` values;
- loading states use Skeleton while retaining an accessible loading status; empty/error states keep their original copy and `ErrorSummary` behavior.

Run the focused tests before changing the surfaces:

```powershell
pnpm exec vitest run --project client src/lib/components/design-system.svelte.spec.ts src/routes/public-pages.svelte.spec.ts
pnpm exec playwright test src/routes/public-registration.e2e.ts
```

**Step 2: Apply Card, Badge, Separator, and Skeleton deliberately**

- Refactor `TournamentCard.svelte` and `TournamentGameRow.svelte` around `Card.Root` and its header/content/footer regions, retaining their existing responsive grids, localized links, dates, fee/capacity formatting, and the `bracket-node` affordance.
- Replace the status `<span>` treatments in the tournament and account-registration surfaces with `Badge`. Use the standard `outline` or `destructive` variants first, then add only semantic status classes for the existing success/warning/open states; never introduce literal palette values.
- Use `Card` on registration detail/list and payment-related surfaces where the current border-and-header treatment is a generic content container. Do not force the account roster or tournament-specific grid into a generic Card layout when it would erase its intentionally structured presentation.
- Replace purely decorative section rules with `Separator`, preserving headings, ordered lists, `<time>`, screen-reader labels, and current page landmarks.
- Replace loading blocks that only communicate pending data with `Skeleton` placeholders plus a visible or screen-reader status message. Do not defer content, change fetch timing, or remove the current redirect/error branches.

**Step 3: Verify components and browser flow**

```powershell
pnpm exec vitest run --project client src/lib/components/design-system.svelte.spec.ts src/routes/public-pages.svelte.spec.ts src/routes/registration-pages.svelte.spec.ts
pnpm exec playwright test src/routes/public-registration.e2e.ts
pnpm check
```

Expected: localized content, route hrefs, registration semantics, and client-side navigation all remain unchanged; only primitive composition and styling change.

## Task 5: Final regression, review, and commit hygiene

**Files:**

- Inspect: all migration files and generated `web/src/lib/components/ui/**` source
- Do not stage: `web/src/lib/components/layout/AppShell.svelte`, `web/src/lib/components/layout/AppShell.svelte.spec.ts`, `.idea/`, or existing untracked plans

**Step 1: Run the complete frontend suite**

```powershell
pnpm exec vitest run --project client
pnpm exec playwright test
pnpm check
```

If Playwright browsers are not installed, run the project's approved setup command and then rerun the targeted suite:

```powershell
pnpm exec playwright install
pnpm exec playwright test
```

Report any unchanged RichText message-typing baseline separately from migration results. Do not fix unrelated server, locale-prefix, or RichText failures in this plan.

**Step 2: Inspect the diff and protected files**

```powershell
git diff --check
git diff -- web/src/lib/components/layout/AppShell.svelte web/src/lib/components/layout/AppShell.svelte.spec.ts
git status --short
```

Confirm that generated source is confined to `$lib/components/ui`, product changes are limited to the specified UI surfaces/tests, and the AppShell diff is identical to the captured user-owned baseline.

**Step 3: Commit only reviewed migration slices**

If the user authorizes commits, create small commits by slice: generated primitives/adapters, form migration, then display migration. Stage exact paths only; do not use `git add -A` or a broad directory that captures the protected AppShell changes. Include the relevant focused test output in each handoff.

**Step 4: Handoff**

Summarize the generated component inventory, the shared adapter compatibility guarantees, the migrated form/display surfaces, exact test evidence, and any pre-existing checks that remain outside the change.
