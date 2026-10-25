# Round robin operation and verification

Round robin groups share the existing competition workspace and public bracket
route. Stage handoffs and Swiss are still separate work.

## Set up and publish

1. Create a competition for the tournament division and open **Stage setup**.
2. Choose **Round robin**, single or double meetings, and **Best of** or **Fixed
   games**. Meetings are per pair, independently of match length. Best-of lengths
   must be positive and odd; fixed-game lengths may be even.
3. Set win/draw/loss points (two decimal places, win > draw >= loss >= 0).
   Configure **Tiebreaker 1–4** in priority order. Blank positions are ignored;
   criteria cannot repeat. Defaults are head-to-head points, game difference,
   games won, and No rule. Four No rule choices leave equal points tied.
4. Select approved entrants, then define groups using `name | qualifying places`,
   one group per line. Each group requires at least two entrants and a qualifying
   count between one and its size. Use seeded snake allocation or manual group
   assignments. **Update group choices** refreshes the manual choices without
   saving a draw and also works without JavaScript. Randomization is saved once
   and is available with snake allocation.
5. Review the saved private draw, group membership, rests, and standings rules.
   Publish only after this review. Membership, meetings, points, rule order,
   qualifying places and stage mode then become immutable.

Before play starts, match lengths can override round lengths, which override the
stage default. Scheduling does not start a match. Starting, entering progress or
finalizing freezes the applied mode and length. An override cannot reinterpret
a started match.

## Results and standings

A best-of result ends when one entrant reaches its winning score. A fixed-game
final must total the configured number of games; equal scores are a draw.
Progress must remain below that total. Scores must be nonnegative integers.

Use group and round selection to browse fixtures, including historical extra
contests. The organizer **View round** form also works without JavaScript. Only
one round of cards is rendered at once. Standings use final ordinary results only. A forfeit receives normal win/loss
points. A double forfeit gives neither side points and records a loss for each.
Only completed played results contribute games won and game difference. An odd
round's absent entrant rests: no scored bye, points, or fabricated games.

Points rank first. Each saved criterion refines only the entrants still tied.
Head-to-head uses their matches and does not restart after separating a subset.
Equal ranks remain equal; seed order controls display only. A tie entirely
inside or outside qualification does not block completion. A cutoff tie does.

## Resolve qualification ties

Open **Standings**, select the group, and choose **Resolve qualification tie**.
Preview and confirm either:

- **Organizer decision:** order every tied entrant once and enter a private
  reason. Only the available qualifying places are selected. Ordinary points
  and ranks stay unchanged; the recorded order is public, the reason is private.
- **Extra matches:** choose an odd best-of length. Two entrants play one match;
  three or more play one round robin mini-table. Rank by match wins, head-to-head
  wins, then game difference. Ordinary group points stay unchanged. A remaining
  cutoff tie requires another explicit decision or extra-match preview.

The stage completes only when every ordinary match and required cutoff is
resolved. Multiple groups do not produce an invented overall champion. A sole
group with one qualifying place may expose that entrant as champion. Qualifiers
are recorded for this stage; moving them into a playoff is not implemented here.

## Correct results

Use the existing **Correct result → Preview correction** workflow. The preview
shows projected standings and qualifiers, invalidated tie decisions, and extra
contests that will become historical, with match identities, current statuses and
preserved score summaries. Confirmation requires a private reason.
A changed losing score can invalidate a decision even if the winner is unchanged
when game metrics participate in ranking.

Unrelated ordinary results remain intact. Superseded tie contests keep their IDs,
scores and applied mode/length and remain readable as history. Their scoring and
schedule actions are disabled. Replacement contests require an explicit new
preview/confirmation. Stale or repeated confirmations are rejected by revision
checks under the division and competition lock; state and history commit together.

## Synthetic fixtures

In a development database, run from `server/`:

```sh
uv run python manage.py migrate
uv run python manage.py seed_dev_data
```

`dev-usec-round-robin` contains fictional teams only:

| Division | Groups | Meetings | Ordinary length | Example states |
| --- | --- | --- | --- | --- |
| Valorant | 3 / 5 | Single | Fixed 2 | Draws, manual qualifier, superseded extra results, pending/live extra contests |
| League of Legends | 4 / 4 | Double | Best of 3 | Completed group, ready/live group, BO5 round override and schedule |

There are 13 and 24 ordinary matches respectively. Repeated seeding preserves
published match IDs/results and tie history while refreshing synthetic registration
snapshots. Existing unrelated fixtures are preserved. No workbook is read.

## Migration and rollback

`competitions.0003_round_robin` is additive and upgrades populated `0002` without
replacing elimination match IDs, results or history. Started legacy modes are
backfilled; fixed-game/tiebreak modes are frozen on future starts. Historical
entrant selections remain protected when an unpublished draw is replaced.

Deploy matching application and database revisions. Back up the database first.
Older code cannot safely operate published round robin data, grouped rounds, or
fixed-game results. After publication, prefer a forward fix. Restoring an older
application requires restoring its matching pre-upgrade database backup; reversing
this migration would remove the new group/tie structures.

## Verification evidence

The implementation uses PostgreSQL for mutation, rollback, migration and race
tests; Chromium component tests cover EN/VI standings; real Django browser tests
cover publication, fixed draws, manual/extra ties, corrections and retained
history.

- Full Django suite: **435 tests passed** on PostgreSQL, including populated
  migration, transaction rollback, tie/correction contention and seeded reruns.
- Full frontend suite: **356 tests passed** across 45 files.
- Real Django/Chromium suite: **17 journeys passed**, including elimination and
  registration regressions, EN/VI, keyboard group selection and 390px local scrolling.
- Svelte check: **0 errors, 0 warnings**. Changed-file Ruff, formatting, ESLint,
  rich-text validation, migration drift and Django system checks passed.

The production build passed. The existing calendar
package circular-import/empty-chunk warnings and Vitest's development-server
`wrapDynamicImport` diagnostics are tooling noise; the test assertions pass.
Deployment against an existing live database remains outside this proof. Ordered stage handoffs are now covered in [the multi-stage operating notes](competition-multi-stage.md).

## Execution decisions

- Kept the existing `feat/tournament-brackets` checkout so changes stay visible in
  the shared workspace; this gives less isolation from concurrent unrelated edits.
- Preserved historical entrant snapshots with `is_selected` instead of deleting
  protected entrants during reselection; historical identities remain stored.
- Capped series lengths and scores at PostgreSQL's small-integer limit (32767);
  unusually long series above that limit require a schema change.
- Normalized played and forfeit wins in fingerprints when no game metric is
  configured; ranking-equivalent corrections preserve decisions. If outcome type
  later becomes a ranking criterion, the fingerprint must change with it.
- Used an explicit **Update group choices** POST for manual assignment without
  JavaScript; changing group definitions requires that extra action.
- Used native select/table elements with installed Field components; custom
  dropdown/table styling would require a separate UI change.
- Applied the same integer/storage bounds to elimination setup after review found
  its legacy validator accepted nonintegers and oversized values. Existing callers
  must pass integer lengths within 1–32767.
- The original slice left stage handoffs/navigation, Swiss, withdrawal/
  disqualification commands, TFT and realtime for later. Stage handoffs/navigation
  are now delivered by the multi-stage slice; the other workflows remain unavailable.
- Reviewed migration/rollback strategy without deploying or executing rollback
  against a live database; live rollout still needs matching code/database backups.
- Disabled the public group selector until hydration attaches its handler;
  early input cannot silently leave the previous group's standings on screen.
  Group switching requires JavaScript; the initially rendered standings remain readable.

- Preserved baseline short match labels, public Changes ordering/pagination and
  generic double-forfeit card labels; their existing presentation limits remain.
- Kept existing calendar build warnings and Vitest development-server diagnostics;
  passing assertions and builds do not guarantee future toolchain compatibility.
- Bounded organizer and public round robin cards by selected round; browsing a
  full schedule requires moving between rounds.

## Final review

One fresh reviewer inspected the complete slice. All five Important findings
were addressed with failing regressions followed by passing checks: stored mode
at Start, blank-line manual group assignments, per-fixture scoring queries,
bounded public rendering, and complete extra-contest correction previews.
The executor also fixed the shared legacy best-of validation issue and bounded
organizer rendering. No minor findings were deferred. Final suite counts above
include those fixes; no second review was dispatched.
