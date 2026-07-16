# Public registration frontend and setup hardening design

**Status:** written for user review  
**Date:** 2026-07-17

## Purpose

Build the first usable public and participant-facing slice of the USEC Tournament Registration Hub. A player should be able to find a published tournament, create or access an account, submit a solo or team registration, provide manual payment evidence when required, and track review status. The backend should expose the public read API, authentication/profile surface, schema documentation, and local setup/settings cleanup needed to support that flow.

This design builds on the approved registration domain model and the implemented Django backend foundation. It does not replace the Django Admin organizer workflow from v1; organizers still review registrations and payment attempts there.

## Scope

This slice includes:

- public tournament discovery and detail pages;
- public API endpoints for published tournaments and tournament games;
- participant account/profile endpoints needed by the SvelteKit client;
- JWT login and refresh wiring for the frontend;
- registration submission UI for individual and team tournament games;
- manual payment proof upload UI for non-zero-fee registrations;
- a "My registrations" participant dashboard;
- API schema and API docs endpoints;
- settings and setup hardening for local development and deploy readiness;
- frontend visual system and reusable page/component boundaries.

This slice intentionally excludes:

- bracket generation, stages, matches, results, standings, and scheduling;
- custom organizer frontend screens;
- payment gateway integration;
- withdrawal, amendment, or roster-claim workflows;
- persistent teams or free-agent/team-matching;
- automated student ID or professional-player verification;
- public display of approved teams/players beyond what is necessary for registration discovery.

## Product flow

The target user journey is:

1. A visitor opens the public site and sees published tournaments.
2. They open a tournament detail page and choose a configured game whose registration window is open.
3. They sign in or create an account.
4. The registration form pre-fills the current user's gamer tag and school for a solo player or captain row.
5. They submit the solo/team roster.
6. If a fee is due, they upload proof or enter a transfer reference.
7. They land on "My registrations" and see the current review status.
8. Organizers continue review and payment decisions in Django Admin.

The frontend should treat Django as the source of truth. Client-side validation is for speed and clarity only; backend service validation remains authoritative.

## Frontend design direction

Use a restrained Swiss tournament operations-board direction rather than a neon esports style. The product is for a university club running real events, so the interface should feel precise, public, and operational.

### Visual tokens

| Role | Token |
| --- | --- |
| Main surface | `#FFFFFF` |
| Secondary surface | `#F7F7F8` |
| Primary text | `#111827` |
| Muted text | `#5B6472` |
| Hairline border | `#D9DEE7` |
| Accent | Yves Klein Blue `#002FA7` |
| Warning/payment accent | Amber `#B45309` |
| Error accent | Red `#B91C1C` |
| Success accent | Green `#047857` |

Typography:

- headings: Manrope;
- body and UI: IBM Plex Sans;
- mono/data: JetBrains Mono only;
- Fira Sans and Fira Mono are not used in this slice.

JetBrains Mono is reserved for registration IDs, status metadata, dates, fees, and small API/schema snippets. It is not used for themed "terminal" copy.

### Layout and interaction

The signature visual move is a bracket-board grid: public tournament cards, tournament detail sections, registration steps, and status timelines sit on a visible 1px rule system. The rules encode structure rather than decoration: tournament → game → registration → payment → review.

Layouts are left-aligned with asymmetric balance. Important dates and statuses may use tabular numerics. Controls use standard copy such as "Sign in", "Create account", "Register", "Upload payment proof", and "Save profile." Avoid ornamental labels, fake telemetry, unicode-glyph icons, and fabricated sample people.

Recommended structure:

```text
Home / tournament list
┌─────────────────────────────────────────────┬─────────────┐
│ USEC Tournament Registration Hub            │ Sign in     │
├─────────────────────────────────────────────┴─────────────┤
│ Published tournaments                                      │
├─────────────────────┬─────────────────────┬───────────────┤
│ Tournament card     │ Tournament card     │ Tournament... │
└─────────────────────┴─────────────────────┴───────────────┘

Tournament detail
┌─────────────────────────────────────────────┬─────────────┐
│ Tournament name, dates, location             │ Status      │
├─────────────────────────────────────────────┴─────────────┤
│ Configured games, windows, fees, capacity                  │
├─────────────────────────────────────────────┬─────────────┤
│ Registration requirements                    │ Register    │
└─────────────────────────────────────────────┴─────────────┘

My registrations
┌─────────────────────────────────────────────┬─────────────┐
│ Registration summary                         │ Status      │
├─────────────────────┬───────────────────────┴─────────────┤
│ Roster              │ Payment / review timeline            │
└─────────────────────┴─────────────────────────────────────┘
```

Motion should be minimal: focus rings, hover border color changes, and short state transitions. Respect reduced-motion settings.

## Frontend architecture

SvelteKit owns public and participant-facing pages. It should call backend APIs through a small typed API client instead of scattering `fetch` calls across route components.

Suggested route groups:

| Route | Responsibility |
| --- | --- |
| `/` | Published tournament overview and sign-in/account entry points. |
| `/tournaments` | Full public tournament list. |
| `/tournaments/[slug]` | Tournament detail and configured game list. |
| `/tournaments/[slug]/games/[gameId]/register` | Auth-gated registration form for one configured tournament game. |
| `/auth/sign-in` | Email/password sign-in. |
| `/auth/register` | Account creation. |
| `/account/profile` | Gamer tag and school defaults. |
| `/account/registrations` | "My registrations" list. |
| `/account/registrations/[id]` | Registration detail, roster, payment evidence action, status timeline. |

Suggested frontend modules:

| Module | Responsibility |
| --- | --- |
| `src/lib/api/client.ts` | Base URL, JSON handling, file upload handling, auth headers, typed error normalization. |
| `src/lib/api/auth.ts` | Sign-in, token refresh, account creation, profile calls. |
| `src/lib/api/tournaments.ts` | Published tournament and tournament-game reads. |
| `src/lib/api/registrations.ts` | Existing participant registration and payment calls. |
| `src/lib/auth/session.ts` | Token storage, current-user loading, sign-out. |
| `src/lib/components/layout/` | Shell, header, language switcher, page grid. |
| `src/lib/components/tournaments/` | Tournament cards, game rows, registration-window status. |
| `src/lib/components/registrations/` | Roster editor, payment upload, status timeline. |
| `src/lib/components/forms/` | Field, error summary, file input, submit button. |

The frontend should keep unfinished registration form state client-side. A backend registration is created only when the user submits the form.

## Backend API additions

Existing private registration endpoints remain under `/api/registrations/`.

Add public tournament read endpoints:

| Endpoint | Access | Responsibility |
| --- | --- | --- |
| `GET /api/tournaments/` | Public | List published tournaments with basic metadata and a compact configured-game summary. |
| `GET /api/tournaments/{slug}/` | Public | Return one published tournament with configured games, registration windows, team-size rules, fee, and availability indicators. |

Do not expose unpublished tournaments through public endpoints. Public tournament responses should not expose registration submitters, payment evidence, review notes, or private participant data.

Add account/auth endpoints:

| Endpoint | Access | Responsibility |
| --- | --- | --- |
| `POST /api/auth/register/` | Public | Create an account with email, password, optional gamer tag, and optional school. |
| `POST /api/auth/token/` | Public | Issue JWT access/refresh tokens using email and password. |
| `POST /api/auth/token/refresh/` | Public | Refresh access tokens. |
| `GET /api/account/me/` | Authenticated | Return the current user's email, gamer tag, and school. |
| `PATCH /api/account/me/` | Authenticated | Update gamer tag and school defaults. |

The registration submission endpoint should continue to accept roster snapshots and must not accept arbitrary `RegistrationMember.user` IDs. The duplicate-player identity-claim workflow remains deferred.

## API schema and docs

Expose drf-spectacular schema and docs:

| Endpoint | Access | Responsibility |
| --- | --- | --- |
| `GET /api/schema/` | Public when `DEBUG=True`; staff-only when `DEBUG=False` | OpenAPI schema. |
| `GET /api/docs/` | Public when `DEBUG=True`; staff-only when `DEBUG=False` | Swagger UI backed by the schema. |

The schema should include the public tournament endpoints, account endpoints, existing private registration endpoints, and payment attempt action. Serializer names should be explicit enough that frontend work can rely on generated or hand-written TypeScript types without guessing.

## Settings and setup hardening

Clean up settings without changing the domain model:

- Parse comma-separated environment variables defensively so empty strings do not become allowed hosts or CORS origins.
- Keep `DEBUG` false by default.
- Require `SECRET_KEY` outside local development, or provide a clearly scoped local-only fallback.
- Add explicit env names for `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, existing DB parts (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`), `MEDIA_ROOT`, and frontend origin.
- Keep JWT as the API authentication mechanism.
- Keep Guardian installed but do not introduce Guardian object-permission usage for v1 registration ownership.
- Keep debug-only media serving local to development.
- Update `.env.example` with all required server variables.
- Add setup notes for running backend checks, tests, migrations, organizer bootstrap, and frontend checks.

The existing blunt CORS comment should be replaced with a neutral explanation of why local SvelteKit origins are allowed.

## Data and error handling

The backend should return field-specific validation errors where practical. The frontend should normalize API errors into:

- field errors shown next to inputs;
- form-level errors shown in an error summary;
- authentication/session errors that direct users to sign in again;
- permission errors that explain the user cannot view or change that registration;
- not-found errors that avoid leaking whether private records exist.

Important validation cases:

- registration window closed or not yet open;
- tournament game capacity reached;
- roster size outside the configured min/max;
- missing or extra team name;
- missing captain or multiple captains;
- missing gamer tag or school snapshot;
- payment evidence submitted for a free registration;
- payment amount/currency mismatch;
- attempting to view another user's registration.

## Internationalization

The frontend already has Paraglide with English and Vietnamese. All UI chrome added in this slice should use localized messages. User-submitted content such as tournament names, team names, gamer tags, and schools is displayed as entered and is not translated.

The implementation should avoid hard-coding English strings inside reusable components where those strings are visible to users.

## Security and privacy

Public pages can show tournament metadata, registration windows, fees, team-size rules, and high-level availability. Private participant pages can show only the authenticated user's registrations.

Never expose through public or participant responses:

- user email addresses other than the current user's own email;
- payment proof file URLs;
- payment references from other users;
- review notes;
- organizer-only audit details;
- unpublished tournament details.

JWT storage should use browser `localStorage` for v1 and be isolated behind `session.ts` so a future move to HTTP-only cookies or stricter refresh handling does not rewrite every page.

## Testing and acceptance criteria

Backend acceptance:

1. public tournament list returns only published tournaments;
2. public tournament detail returns 404 for unpublished or missing slugs;
3. tournament detail includes configured games, registration windows, team-size rules, and fee fields;
4. account registration creates an email-login user and rejects duplicate email addresses;
5. current-user endpoint requires authentication and returns only the current user's public profile defaults;
6. profile update changes gamer tag and school only;
7. schema and docs endpoints are mounted and include tournament, account, registration, and payment endpoints;
8. settings parsing ignores empty CORS and allowed-host entries;
9. existing registration, payment, ownership, and organizer tests continue to pass.

Frontend acceptance:

1. SvelteKit check passes;
2. home and tournament list render empty states without fabricated tournament data;
3. tournament detail renders real API data and handles not-found/unpublished responses;
4. unauthenticated users are sent to sign in before registering;
5. registration form supports solo and team configurations from backend min/max settings;
6. form errors map backend validation messages to visible field or form errors;
7. "My registrations" lists only the current user's registrations;
8. registration detail shows roster snapshots, fee snapshot, status, and status timeline;
9. payment proof upload is available only when a fee is due;
10. visible UI strings are localized through the existing English/Vietnamese message system;
11. the rendered UI follows the approved Manrope / IBM Plex Sans / JetBrains Mono font system and Swiss operations-board visual direction.

## Verification commands

Run backend commands from `server/`:

```powershell
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run python manage.py test -v 2
uv run ruff check .
```

Run frontend commands from `web/`:

```powershell
pnpm check
pnpm lint
pnpm test:unit -- --run
```

If browser-facing routes are implemented with meaningful flows in this slice, add Playwright coverage for the public tournament detail, registration auth redirect, and "My registrations" happy path.

