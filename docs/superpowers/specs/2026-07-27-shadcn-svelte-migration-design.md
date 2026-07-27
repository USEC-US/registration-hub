# shadcn-svelte UI Migration Design

## Goal

Replace most handcrafted UI primitives with shadcn-svelte components while retaining the USEC visual system defined in `web/src/routes/layout.css`.

## Design Direction

The migration uses the installed shadcn-svelte registry and its locally generated components as the implementation foundation. It does not adopt a separate stock theme: shadcn-svelte components inherit the existing semantic tokens, fonts, radii, and light/dark values already defined in `layout.css`.

The existing tournament-specific visual language remains intentional and custom:

- USEC brand header and secondary navigation;
- grid-board and bracket-node motifs;
- tournament-specific page structure and content hierarchy.

shadcn-svelte supplies reusable interaction and content primitives within that language.

## Scope

### Shared primitives

Add or standardize local shadcn-svelte components for:

- Button, Input, Label, Textarea, Select, Checkbox, and form field composition;
- Alert for form and page errors;
- Card, Badge, Separator, and Skeleton for repeated content states;
- Dropdown Menu and Navigation Menu where they improve existing navigation behavior.

Retire handcrafted styling from `Field.svelte` and `ErrorSummary.svelte` by rebuilding them as thin, application-specific wrappers over these primitives. Keep their public behavior, bindable values, error IDs, and accessibility contracts intact unless a caller is migrated in the same step.

### Feature migration order

1. Establish the shadcn-svelte primitives and token compatibility.
2. Migrate shared form and feedback wrappers.
3. Migrate authentication, profile, registration, and payment forms.
4. Migrate tournament cards/game rows, roster editing, status timeline, and page sections.
5. Apply shadcn-svelte navigation utilities where appropriate without replacing the bespoke app shell or the already user-edited navigation layout.

Each slice is independently testable and committed separately. No backend, API contract, route, localization message, or session behavior changes are in scope.

## Styling Rules

- Reuse `--background`, `--foreground`, `--primary`, `--border`, `--muted`, `--destructive`, existing font tokens, and radius tokens from `layout.css`.
- Prefer shadcn-svelte component variants and `class` composition over new one-off utility stacks.
- Keep component overrides limited to product-specific layout and the existing tournament motifs.
- Preserve the current responsive behavior, visible focus treatment, reduced-motion rules, and semantic HTML.

## Verification

- Add or update focused browser tests before changing each shared primitive or migrated feature.
- Run the relevant client suite for every slice and the complete client suite at the end.
- Run `pnpm check`; report the known RichText message-typing baseline if it remains unchanged.
- Inspect the final diff to ensure no user-owned navigation edits are staged accidentally.
