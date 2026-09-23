# Organizer registration navigation

The next organizer slice extends Django admin: show linked division and total
registration counts on tournament lists/detail pages and linked registration
counts on division lists/detail pages. Counts include all statuses, including
rejected and expired entries; they describe review records, not occupied places.

Use ORM annotations and native admin changelist filters. Count distinct divisions
so joins to registrations cannot inflate totals. Select related tournament/game
rows for division lists. Unsaved objects display a dash. Existing admin gates
continue to protect both source pages and linked destinations; no private contact
or payment fields are added to these summaries.

Alternatives: a separate dashboard duplicates navigation and permission handling;
per-row count queries grow with the list size. Neither is needed here. There are
no new dependencies, models, migrations, public endpoints, or status transitions.

Acceptance: zero/multiple divisions, multiple registrations and all statuses count
correctly; links reach exactly the intended tournament/division records; detail
pages render; unauthorized staff cannot use links to bypass organizer membership
or registration model permissions; summary rendering uses no per-row queries.
