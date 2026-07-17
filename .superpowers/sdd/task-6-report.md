# Task 6 report: frontend design system

## Outcome

Implemented the HCMUS USEC tournament operations visual system, a typed root shell, localized English/Vietnamese UI copy, and reusable typed form, tournament, and registration-status components.

The design uses paper white (`#fff`) inside a muted operations board (`#f7f7f8`), near-black ink (`#111827`), restrained gray rules (`#d9dee7`), and HCMUS blue (`#002fa7`). Manrope carries headings, IBM Plex Sans carries interface copy, and JetBrains Mono is limited to IDs, dates, fees, capacity, and status data. The shell and components use square corners, 1px bracket rules, and small blue nodes at real brand/navigation and tournament/game/action intersections.

## Inherited RED

The focused browser spec was already established before implementation. It failed while resolving the missing `StatusTimeline.svelte`; the existing 13 unit tests passed. That was the expected feature-missing failure and served as the RED gate.

The first post-component run surfaced two test-contract issues and one compiler diagnostic:

- `vitest-browser-svelte` treats `events` as a reserved Svelte mount option, so the timeline test now passes it explicitly under `{ props: { events } }`.
- A false top-level Svelte `{#if}` leaves an internal comment anchor. The empty-summary assertion now checks `childElementCount === 0`, preserving the contract that no summary element renders without asserting against framework internals.
- `Field` originally captured the initial `name` in a constant. Its error ID is now `$derived`, so label/error associations stay reactive and the Svelte warning is gone.

Each correction was rerun against its exact focused test before the combined browser spec.

## GREEN implementation

- Added `AppShell` with typed snippet children, skip link, responsive rule-based navigation, SvelteKit-resolved internal links, and a visible accessible EN/VI locale switch.
- Mounted the shell from the root layout and kept the favicon source as a real tracked asset.
- Added typed `Field`, `ErrorSummary`, `TournamentCard`, `TournamentGameRow`, and `StatusTimeline` components.
- Added English and Vietnamese navigation, action, form, empty-state, tournament, registration-state, and status-timeline messages.
- Replaced generic theme defaults with the brief's exact token and font system, visible focus treatment, reduced-motion handling, grid-board utility, and blue bracket-node signature.
- Added JetBrains Mono as a frontend dependency and retained the updated workspace lockfile.
- Kept generated Paraglide output untouched and excluded it narrowly from Prettier and ESLint. Generated Inlang metadata is excluded from Prettier.
- Mechanically formatted the requested handwritten utility and the three inherited API files that blocked the project-wide lint baseline; their API diffs contain line wrapping only.

## Design self-critique

The strongest choice is the bracket structure: borders and blue square nodes encode actual transitions between tournament, game, registration action, and status rather than acting as detached decoration. The type roles also remain disciplined; monospaced text is not used as a general tech aesthetic.

The system deliberately spends its visual emphasis on those intersections. The surrounding shell stays left-aligned, quiet, square, and information-first, avoiding gradients, neon, rounded generic cards, fake content, icon ornament, and unnecessary motion. Mobile layouts collapse by preserving the same rule hierarchy rather than turning every section into an unrelated card.

One temporary compromise is explicit `Pathname` casts for navigation destinations implemented in later tasks. Every URL still passes through SvelteKit's `resolve`; the casts can be removed when those routes enter the generated route union. Full destination-page visual QA also belongs to those later route tasks, while this slice is covered by browser component semantics, Svelte diagnostics, and lint.

## Verification

Run from `web/` after all fixes:

- `pnpm exec vitest --run src/lib/components/design-system.svelte.spec.ts` — 1 file passed, 4 tests passed.
- `pnpm test:unit -- --run` — 6 files passed, 17 tests passed.
- `pnpm check` — 0 errors and 0 warnings.
- `pnpm lint` — all matched files use Prettier style; ESLint exited 0 with no diagnostics.

No generated `web/src/lib/paraglide/*` file was edited or staged. Root `.gitignore`, `server/.gitignore`, unrelated docs, and server/temp paths remain outside the Task 6 staging scope.
