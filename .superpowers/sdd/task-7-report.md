# Task 7 report: public tournament pages

## Outcome

Implemented SSR-capable public routes for the home page, tournament index, and tournament detail. All three route loads use SvelteKit's request-scoped `fetch` through the typed tournament API wrappers, so the same universal load code can run during server rendering and client navigation.

The pages render only backend tournament data. They include localized English/Vietnamese chrome, meaningful document metadata, empty states, semantic heading levels, separate machine-readable start/end times, configured game rows, and registration links only when the API marks a game open. Blank locations are described as unannounced rather than fabricated as online. Closed, full, and not-yet-open games remain visible without a registration action. Tournament API 404 responses map to a localized route 404; other failures propagate unchanged.

Tournament times use UTC API strings unchanged in `<time datetime>` attributes. A typed Temporal utility converts each instant into a validated display timezone. The root server layout reads a non-sensitive timezone cookie and falls back to `Asia/Ho_Chi_Minh`, keeping SSR and hydration deterministic. After mount, the browser detects its zone with `Temporal.Now.timeZoneId()`, persists it, and invalidates only the root timezone dependency when it differs. Date-time copy includes a short timezone label.

## TDD evidence

The initial focused RED run failed because the three route modules did not exist and the tournament wrappers ignored the supplied SvelteKit fetch. Two wrapper assertions failed and both route test suites failed module resolution, while existing code remained untouched.

The first GREEN attempt passed 10 of 12 tests. It exposed an isolated loader test without a Paraglide locale and the inherited card's fixed `h2`. The test now establishes an English locale, production 404 copy remains localized, and `TournamentCard` accepts a typed optional `headingLevel` while preserving `2` as its default.

Review hardening added RED coverage before each presentation fix: localized blank locations, UTC-boundary timezone conversion and invalid fallback, server cookie loading and client invalidation, separate semantic time elements, body typography, the odd mobile metadata row, and unavailable registration states. The final focused review run passed 5 files and 26 tests.

## Browser navigation and SSR scope

The Playwright smoke enters through the existing static `/demo/playwright` route, follows the real AppShell brand link into `/`, and then follows the real tournament action into the detail route. The Playwright web server builds with `PUBLIC_API_BASE_URL=http://localhost:4173/api`, allowing those browser-side universal-load fetches to be intercepted same-origin.

The smoke asserts exactly one document request (the static entry) plus one ordered collection request and one detail request. This proves those two transitions used SvelteKit client navigation and each universal page load issued one API request. It does not isolate timezone invalidation on an API-backed page or execute the public routes' SSR branch. The routes remain SSR-capable because they use universal `+page.ts` loads, contain no `ssr = false` opt-out, and produce server entries in the production build.

## Verification

- Focused Task 7 review Vitest: 5 files passed, 26 tests passed.
- Full unit/browser suite: 12 files passed, 46 tests passed.
- `pnpm check`: 0 errors and 0 warnings.
- `pnpm lint`: Prettier and ESLint exited 0.
- `pnpm build` with the documented production API base: exited 0.
- `pnpm exec playwright test src/routes/public-registration.e2e.ts`: 1 test passed using the installed Chromium browser.
- `git diff --check`: clean.

No generated Paraglide file was edited or staged. Unrelated documentation and visual assets remain outside Task 7 staging.
