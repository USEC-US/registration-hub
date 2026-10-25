# Competition core and single-elimination implementation plan

Date: 2026-09-25. Branch: `feat/tournament-brackets`.

Status: **Approved on 2026-09-25.** Product implementation may proceed under
this plan, as required by the approved
[competition-core design](../specs/2026-09-23-competition-core-design.md).

Implementation status: **Implemented and focused-validated on 2026-09-25.** The
commands, results, and repository-wide baseline exceptions are recorded in the
[single-elimination testing guide](../../testing/competition-single-elimination.md).

This plan delivers the first complete competition slice: shared persisted state,
one standalone single-elimination stage, organizer operation in Django Unfold,
published public HTTP reads, a SvelteKit bracket, and safe result correction.
It satisfies C1-C5, E1-E2, the single-elimination portions of A1-A5 and P1-P5,
and the applicable V1-V5 checks in [BRACKET-TODO.md](../../BRACKET-TODO.md).

## Observable acceptance

An authorized organizer can:

1. Create one competition for a division, select unique approved registrations,
   configure a single-elimination stage and best-of series rules, then save manual
   seeds or one persisted random order.
2. Preview the exact bracket privately, publish it once, schedule matches, apply
   round or match series-length overrides before play, save progress, and finalize
   results through guarded commands.
3. Correct a published result after downstream play only after reviewing and
   confirming every affected reset. Previous outcomes remain in Changes.
4. Complete the bracket with a champion or an explicit no-champion outcome.

A spectator can open
`/tournaments/[slug]/games/[gameId]/bracket`, read only published fixtures,
schedules, effective series lengths, scores, advancement, historical matches,
and public Changes, and use the page on mobile or by keyboard in English or
Vietnamese. No response or page data contains private registration, payment,
contact, audit-actor, or internal-note fields.

## Deliberate boundaries

- Deliver one standalone single-elimination stage. Multi-stage handoffs, double
  elimination, round robin, Swiss, qualification ties, and placement matches
  follow in their own slices.
- Keep normal HTTP authoritative. Do not add Channels, Redis, polling, SSE, or
  WebSockets.
- Do not add NetworkX; it is needed only when Swiss pairing begins.
- Use Django admin commands and server-rendered templates. Do not add an organizer
  Svelte application or a generic workflow framework.
- Keep registrations and tournament catalogue behavior unchanged except for a
  division-to-competition admin link and a public bracket link.

## 1. Establish the app and shared ownership

**Owned files:** new `server/competitions/__init__.py`, `apps.py`, `models.py`,
`migrations/0001_initial.py`, and `tests/test_models.py`; modify
`server/config/settings.py`.

- Add `competitions` to `INSTALLED_APPS`; do not add a dependency.
- Add the first-slice records: `Competition`, `CompetitionEntrant`, `Stage`,
  `StageDraw`, `StageEntry`, `Round`, `Match`, `MatchSlot`, and `ChangeSet`.
- Keep `Competition` one-to-one with `TournamentGame` and store its monotonic
  revision there. Protect registrations and retained history from cascading
  deletion. Use database constraints for unique stage positions, draw versions,
  seeds, match codes, and exactly one slot position per match.
- Store typed lifecycle, format, series-mode, and outcome fields. Use validated
  JSON only for immutable command snapshots and separate public/private Changes
  payloads. Do not add `StageGroup` or `TieResolution` before their slices.
- Permit ordered stage rows in the schema, but first-slice commands accept one
  standalone single-elimination stage only.
- Test constraints, protected references, entrant display snapshots, and stable
  history. Generate and review the additive migration before continuing.

**Proof:**

```bash
cd server
uv run python manage.py test competitions.tests.test_models -v 2
uv run python manage.py makemigrations --check --dry-run
```

## 2. Centralize organizer authorization

**Owned files:** new `server/config/organizers.py` and
`server/config/tests/test_organizers.py`; modify `server/tournaments/admin.py`
and `server/registrations/services.py` without changing their behavior.

- Move the existing active-user, staff, Organizers-group, superuser, and Django
  permission checks into `is_organizer_staff()` and `require_organizer()`.
- Reuse those functions from current tournament admin, registration commands,
  and every competition command. Keep object/state validation inside the owning
  command.
- Cover inactive users, unrelated staff, missing permissions, valid organizers,
  and superusers before competition code relies on the shared helper.

## 3. Generate deterministic single-elimination draws

**Owned files:** new `server/competitions/elimination.py` and
`server/competitions/tests/test_elimination.py`.

- Implement one pure generator using the approved recursive seed order and the
  smallest containing power-of-two field.
- Represent unknown sources separately from known empty seeds. Resolve structural
  byes without creating played scores or fake losers.
- Return plain immutable draw data for commands to persist; do not introduce a
  format interface, registry, or plugin system.
- Cover 2/3/4/5/8/16 entrants, exact seed positions, byes, winner routes,
  acyclic dependencies, and no entrant appearing twice in a round.

## 4. Implement setup, preview, and publication commands

**Owned files:** new `server/competitions/commands.py` and
`server/competitions/tests/test_commands.py`.

- Add named functions for create/configure competition, select entrants, save
  manual or random order, preview, and publish. Use `secrets.SystemRandom` for a
  random draw and persist the result so refresh never reshuffles it.
- Accept an actor and expected revision. In one `transaction.atomic()` block,
  lock `TournamentGame`, then `Competition`, then affected rows by primary key;
  validate permission, scope, state, and revision before mutation.
- Select only unique `APPROVED` registrations from the same division. Recheck
  eligibility at publication and freeze the approved public display snapshot.
- Validate the 2-256 entrant limit, match budget, best-of rules, unique seeds,
  acyclic slots, and a complete saved preview. No GET request creates state.
- Append one immutable `ChangeSet` and increment the competition revision once
  per successful command. Failed and repeated commands leave no success history.
- Document the division-wide lock with the approved `ponytail:` throughput note.

## 5. Implement match operation and correction

**Owned files:** continue `server/competitions/commands.py`; add focused cases to
`server/competitions/tests/test_commands.py` and PostgreSQL concurrency cases in
`server/competitions/tests/test_concurrency.py`.

- Add commands for schedule, stage/round/match length override, start, save
  progress, finalize, preview correction, and apply correction.
- Resolve effective length as match then round then stage. Capture the applied
  length at first progress/finalization and reject any inherited edit that would
  reinterpret a started match.
- Validate decisive best-of scores and administrative bye/double-forfeit paths.
  Finalization and winner advancement commit atomically and cannot advance twice.
- Build correction impact on the server. Sign the canonical preview with
  `django.core.signing`; under the same lock order, recompute and reject stale or
  changed impact before applying it.
- Reset only transitive matches whose participants changed, retain unaffected
  match IDs/results, preserve superseded outcomes in Changes, and allow explicit
  no-champion completion when no survivor exists.
- Prove stale revisions, duplicate POSTs, rollback, simultaneous finalization,
  correction after played dependants, and registration-approval/publication races
  against PostgreSQL.

## 6. Add least-privilege Unfold workflows

**Owned files:** new `server/competitions/admin.py`, `forms.py`, and templates
under `server/competitions/templates/admin/competitions/`; modify
`server/tournaments/admin.py`,
`server/registrations/management/commands/bootstrap_organizers.py`, and its
existing command tests; add `server/competitions/tests/test_admin.py`.

- Grant organizers view permissions for competition records and Changes,
  `add/change_competition`, and `change_match`; grant no delete or direct history
  editing permissions.
- Link the competition workspace from `TournamentGameAdmin`.
- Build one competition workspace for setup, entrants, saved preview, bracket,
  matches, and Changes. Use explicit GET confirmation plus CSRF-protected POST
  forms that call commands; generated records stay read-only in generic admin.
- Add match scheduling, series override, progress/final result, and correction
  impact forms. Show stale-state validation and destructive reset consequences.
- Verify list/detail/action URLs and services independently enforce organizer
  membership, Django permissions, object scope, state, and request method.

## 7. Expose allowlisted public reads

**Owned files:** new `server/competitions/serializers.py`, `views.py`, `urls.py`,
and `tests/test_api.py`; modify `server/config/api_urls.py`.

- Implement the approved competition overview, stage, round, match, and paginated
  Changes endpoints. Use explicit `Serializer` fields rather than exposing models
  through a generic history serializer.
- Return 404 for unpublished parent tournaments, draws, stages, rounds, matches,
  and direct IDs. Keep superseded published matches available only as labelled
  history; superseded drafts remain private.
- Construct public Changes from its separate safe payload. Exclude actors, notes,
  names, birth dates, student IDs, contact/account data, payment data, and draft
  events at the serializer boundary.
- Read each snapshot in a PostgreSQL read-only repeatable-read transaction and
  include `competition_revision` in every response.
- Cover visibility, allowlists, history, pagination bounds, query consistency,
  and anonymous access. No public endpoint mutates state.

## 8. Build the public bracket route

**Owned files:** new `web/src/lib/api/competitions.ts`, its focused test, and
`web/src/routes/tournaments/[slug]/games/[gameId]/bracket/+page.ts` and
`+page.svelte`; modify `web/src/lib/api/types.ts`,
`web/src/lib/components/tournaments/TournamentGameRow.svelte`,
`web/messages/en.json`, and `web/messages/vi.json`; add focused route/component
tests.

- Add typed fetchers for the public snapshot and cursor-paginated Changes. Treat
  an unpublished or missing competition as an ordinary unavailable page state.
- Add one bracket link beside the existing registration action. The bracket page
  renders the current standalone stage, round columns, stable match codes,
  effective series lengths, schedules, scores, winners, byes, historical labels,
  and public Changes.
- Use semantic headings, lists/tables, escaped labels, native CSS connectors,
  horizontal scrolling on wide brackets, and a mobile round/list presentation
  with logical focus order. Add no canvas or bracket dependency.
- Refetch on a revision mismatch; after two failed attempts show a refresh state
  rather than combining inconsistent data. Use explicit refresh only.
- Cover unavailable, ready, live, complete, corrected, empty/error, mobile,
  keyboard, English, and Vietnamese states.

## 9. Exercise and document the complete slice

**Owned files:** extend `server/registrations/dev_seed.py` and its tests with one
isolated published bracket scenario; add
`docs/testing/competition-single-elimination.md` and a focused Playwright journey.

- Seed approved entrants and a realistic uneven bracket without changing the
  existing registration fixtures' behavior.
- Run a real Django/Unfold/Svelte journey: create/select/seed, preview, publish,
  schedule, score, advance, correct a played dependency, inspect organizer and
  public Changes, and finish the bracket.
- Check view-only and partial-permission organizers, direct URLs, public privacy,
  mobile layout, keyboard operation, and both locales.
- Record the PostgreSQL, backend, frontend, migration, and browser evidence in
  the testing document; then update C1-C5, E1-E2, A1-A5, P1-P5, and V1-V5 only
  for behavior actually proven.

**Final proof:**

```bash
cd server
uv run python manage.py test competitions config registrations tournaments -v 2
uv run python manage.py makemigrations --check --dry-run
uv run ruff check .

cd ../web
pnpm check
pnpm test:unit -- --run
pnpm lint
pnpm test:e2e
```

## Merge order

1. Schema and shared organizer authorization.
2. Pure generator and setup/publication commands.
3. Match lifecycle, corrections, and concurrency proof.
4. Unfold operation.
5. Public API and Svelte route.
6. Full workflow evidence and roadmap reconciliation.

Each step keeps its focused tests green. Do not merge a backend-only generator,
mock-only bracket, or direct-edit admin as a completed first slice.
