# Test Health Remediation Design

## Goal

Restore reliable frontend and backend quality gates while preserving Vietnamese as the unprefixed, base locale.

## Decisions

- Vietnamese remains the `baseLocale`; bare routes and default rendered copy are Vietnamese. English routes use the `/en/` prefix.
- Navigation and page tests will assert the configured locale policy instead of changing working localization code.
- Browser-component tests receive one shared public API environment value through Vitest configuration.
- E2E tests use an existing public route as their client-navigation starting point; no production-only demo route is added.
- Browser installation is an explicit setup command. The E2E test command only runs tests.
- Roster text input events replace the edited member in the bound array so Svelte tracks the update.
- OpenAPI warnings are fixed with schema-only metadata and a schema-safe empty queryset; registration access rules and API responses remain unchanged.

## Frontend Test Contract

Unit and browser tests must use Vietnamese copy and bare URLs when exercising the default locale. Tests that explicitly choose English must expect `/en/` URLs and English copy. Unsafe redirect assertions continue to verify that invalid destinations fall back to the Vietnamese registration route; the tests do not weaken redirect validation.

The Vitest browser project will load a shared setup module that mocks `$env/dynamic/public` with `PUBLIC_API_BASE_URL: '/api'`. This unblocks component imports without changing production API configuration.

The Playwright tests will start from the existing sign-in page, use Vietnamese accessible names, and retain assertions that public navigation is client-side and that unauthenticated registration redirects without a document navigation to the registration form. `test:e2e` will run `playwright test`; a separate installation script remains available for fresh environments.

## UI Reactivity

`RosterEditor` will replace an individual member object through an indexed update helper on each text input. The helper preserves the other roster fields and assigns a new bound members array, matching the existing immutable captain-selection update.

## Backend Schema Quality

`RegistrationViewSet` will expose an empty schema-only queryset while retaining its request-user-filtered `get_queryset`. The registration ID parameter and colliding status enums will receive explicit drf-spectacular metadata so schema generation is deterministic and warning-free.

## Verification

- Frontend: `pnpm run check`, `pnpm run lint`, `pnpm run test:unit`, and `pnpm run test:e2e`.
- Backend: `python manage.py test -v 2 --keepdb --noinput`, `ruff check .`, and `python manage.py makemigrations --check --dry-run`.
- The final Django test output must have no drf-spectacular warnings.

## Scope Boundaries

This change does not alter public routing, user-facing copy, authentication semantics, API contracts, database models, or the existing E2E API stubbing strategy.
