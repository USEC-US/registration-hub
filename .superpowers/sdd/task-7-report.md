# Task 7 report: public tournament pages

## Outcome

Implemented SSR-capable public routes for the home page, tournament index, and tournament detail. All three route loads use SvelteKit's request-scoped `fetch` through the typed tournament API wrappers, so the same code works during server rendering and client navigation.

The pages render only backend tournament data. They include localized English/Vietnamese chrome, meaningful document metadata, empty states, semantic heading levels, machine-readable tournament dates, configured game rows, and registration links only when the API marks a game open. Tournament API 404 responses map to a localized route 404; other failures propagate unchanged.

## TDD evidence

The initial focused RED run failed because the three route modules did not exist and the tournament wrappers ignored the supplied SvelteKit fetch. Two wrapper assertions failed and both route test suites failed module resolution, while existing code remained untouched.

The first GREEN attempt passed 10 of 12 tests. It exposed an isolated loader test without a Paraglide locale and the inherited card's fixed `h2`. The test now establishes an English locale, production 404 copy remains localized, and `TournamentCard` accepts a typed optional `headingLevel` while preserving `2` as its default. The final focused run passed all 12 tests.

## SSR and Playwright strategy

Playwright cannot intercept a server-side API fetch triggered by a direct navigation. The smoke therefore keeps SSR enabled, enters through the existing static `/demo/playwright` route, and follows the real AppShell brand link into `/`. The Playwright web server builds with `PUBLIC_API_BASE_URL=http://localhost:4173/api`, allowing the browser-side load fetch to be intercepted same-origin. It then follows the real tournament action into the detail route.

The smoke experimentally asserts exactly one document request (the static entry) plus the ordered collection and detail API requests. This proves both public transitions used SvelteKit client navigation instead of weakening the routes with an SSR opt-out.

## Verification

- Focused Task 7 Vitest: 3 files passed, 12 tests passed.
- Full unit/browser suite: 9 files passed, 33 tests passed.
- `pnpm check`: 0 errors and 0 warnings.
- `pnpm lint`: Prettier and ESLint exited 0.
- `pnpm build` with the documented production API base: exited 0.
- `pnpm exec playwright test src/routes/public-registration.e2e.ts`: 1 test passed using the installed Chromium browser.
- `git diff --check`: clean.

No generated Paraglide file was edited or staged. User-owned `.gitignore`, `server/.gitignore`, and unrelated documentation remain outside Task 7 staging.
