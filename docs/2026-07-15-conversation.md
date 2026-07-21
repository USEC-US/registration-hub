# Phase 0 - Domain, before any code
## Note
- Full JAMStack: API (Django REST Framework) consumed by Frontend (SvelteKit)
- Not using the default Django Admin at all, everything will be built from the entire Frontend.
## Who registers — individuals, teams, or both? If teams, is there a captain/roster concept with min/max size?
- Both can register. They will still have to create an account, but with Team, the person who is registering can either be their manager, or as the captain themselves.
- Min/Max team size is defined PER TOURNAMENT and PER GAME.
## One tournament or many — is "Tournament" itself a model (with its own registration window, rules, capacity), or is this hub for a single recurring event?
- Many Tournaments.
## Approval flow — does registration auto-confirm, or does an organizer review/approve/reject submissions?
- They need to review their submission, to be more sure, especially for payment stuff, as they might get lost if not checking, and pro player check, if they can fake info.
## Money — any fees involved, or is this pure logistics (no payment integration)?
- Depends on the tournament, and the fund, etc...
## Accounts — do registrants need to log in and see "my registration," or is it a public form + admin-only backend (Django admin as the review UI)? This one matters a lot technically (see below)
- Favor those has an account to log in to their account to automatically fill the registration form for the captain/solo player, and an entire list of My Registration.
## Constraints/eligibility — student ID validation, one registration per person, deadlines per tournament?
- One registration per person.
- Realistically to verify every single Student ID is a pain, each school has different format of it.
- Deadlines per tournament.
- etc. will flush out later.
## What's public — do non-registered visitors see anything (schedule, bracket, results), or is the whole site gated?
- Schedule, bracket, result, players and teams, all the tournament info except for sensitive info.
## Bilingual scope — you've already got en/vi via paraglide. Is that just UI chrome, or does user-submitted content (team names, etc.) also need to work across both?
- Just the UI and everything. Users/Teams/Players don't need to be translated. Of course.

Show less
Q: Registration window (open/close) and team capacity — same scope as fee (per-Division), or stay at the Tournament level?
A: Also Division-scoped — each division has its own open/close dates and team cap


Reconciled division-level scoping for registration windows and capacity constraints
Reconciled division-level scoping for registration windows and capacity constraints
That's consistent and closes Phase 0 as a fully decided domain model. Here's where everything lands, pulled together from the whole thread:

Entities

Game — catalog lookup (name).
Tournament — the event itself. Just identity/general info now — no registration window, capacity, or fee; those all moved down to Division.
Division — Tournament + Game join. Carries team_size_min/team_size_max (equal values = individual division, unequal = team division — no separate flag needed), its own registration_open/registration_close, capacity (max teams/entrants), and fee.
Registration — one per (User, Division), enforced at that granularity, not per-tournament. Owns the whole team directly for v1 (no separate Team entity — deferred until ghép-team lands). Has a status (submitted → under review → approved/rejected) and payment fields, kept loose enough (payment_proof optional, not hard-required) to not preclude a gateway later.
RosterMember — belongs to a Registration, only relevant when team_size > 1. user nullable (unclaimed free-text entry vs. claimed account). For team_size == 1 divisions, skip this entirely — Registration.user is the participant.
Surfaces

DRF API: participant-facing only — submit registration, "My Registrations," public read views (schedule/bracket/results/teams/players).
Django Admin: everything organizer-facing — review, approve/reject, payment verification, eligibility judgment calls.
Explicitly deferred, not designed for now

Ghép-team / free-agent matching (comes back later as a real but bounded migration: add Team entity, backfill 1:1, repoint roster FKs).
Automated student ID / eligibility verification (manual review only).
Payment gateway integration (manual proof-upload assumed for now; schema stays flexible).
Still soft, not blocking, worth a line in your doc so you don't forget

Public display identity — real name vs. a separate gamer-tag/display-name field (I'd lean toward the latter given this is public-facing, but you haven't committed either way).
Whether Django Admin access needs per-tournament scoping once/if you're not the only organizer — fine to punt since it's a permissions concern, not a schema one.
That's a complete enough picture to start writing your actual Phase 0 doc and then move into models. Ping me with the draft whenever — I'll go through it the same way: gaps, contradictions, hidden cost calls-out, not a rewrite.

Public display would be for player identity: GamerTag (title on top line), School (subtitle on bottom line).
For now, maybe get some roles and permissions defined good enough and we'll come back later.

Architected registration data model and baseline permission framework
Architected registration data model and baseline permission framework
GamerTag + School — clear, and sensible for an esports-adjacent public display (nobody wants a real name plastered on a public bracket page). One real design decision this creates that you haven't addressed: where does this data actually live — on the User profile as a live value, or copied onto the Registration/RosterMember at submission time?

This isn't cosmetic. If it's a live reference to the profile, then when someone changes their GamerTag next season, every past tournament's public page silently shows the new tag retroactively — which is wrong for a historical record (same reason an e-commerce order stores the price paid, not a live link to the current price). My recommendation: keep GamerTag/School on the User profile as the default (that's what powers the "autofill the form" convenience you wanted earlier), but copy the value into the Registration/RosterMember at submission time as the actual displayed value for that tournament. Past tournaments then stay accurate even if someone rebrands later.

Q: GamerTag/School on public displays: snapshot at registration time, or live reference to the current profile?
A: Snapshot at submission, but on their profile we also as "Formerly known as <dropdown>"


Validated snapshot design and deferred "formerly known as" feature implementation
Validated snapshot design and deferred "formerly known as" feature implementation
That's a nice feature, and it actually validates the snapshot decision — if you'd gone with a live reference instead, "Formerly known as" would be structurally impossible to build (there'd be no historical record to look back at, just one current value). With snapshotting, it comes almost for free: no new field needed on User at all. It's just a query — distinct gamer_tag values pulled from that user's own past Registration/RosterMember snapshots, ordered by time, excluding whatever their current live profile tag is. Purely a derived read, not stored state.

One light UX note, not blocking anything: if someone uses different tags per game (common — one handle for Valorant, another for a fighting game), decide later whether "formerly known as" mixes all of them together or is scoped per-game. Doesn't affect the schema either way since it's just a query over existing data — pure UI decision, safe to punt.

With that, Phase 0 is genuinely complete. Full picture, all in one place:

Entities

Game — catalog lookup.
Tournament — event identity/general info only.
Division — Tournament + Game join. team_size_min/max (equal = individual, unequal = team), registration_open/close, capacity, fee — all division-scoped.
Registration — one per (User, Division). Owns the team directly for v1 (no separate Team entity — ghép-team deferred). Status workflow, payment fields (loosely coupled, not hard-required, to leave room for a gateway later), snapshotted gamer_tag/school at submission time.
RosterMember — belongs to a Registration, only exists when team_size > 1. user nullable (unclaimed free-text vs. claimed), also carries snapshotted gamer_tag/school.
User — has gamer_tag/school as live defaults (autofill source), distinct from the snapshotted values on each Registration/RosterMember.
Roles/permissions baseline ("good enough for now")

Anonymous — not an account role; AllowAny on public read endpoints (schedule/bracket/results/players/teams) in the DRF API.
Authenticated User — no group needed, just object-level ownership (registration.user == request.user) via a custom DRF permission class. Can manage only their own Registrations.
Organizer — is_staff=True + one flat "Organizers" Django Group with model permissions on Tournament/Division/Game/Registration/RosterMember. Grants Django Admin access, where review/approval/payment-verification happens. One tier only — don't split into finer permission levels until you actually have multiple staff stepping on each other.
Superuser — Django's built-in, effectively just you.
Explicitly deferred

Ghép-team/free-agent matching, payment gateway integration, automated ID/eligibility verification, per-tournament Organizer scoping, claimed-roster-member read access to registrations they didn't create.
That's a genuinely complete Phase 0 — every fork we've walked through resolves cleanly into the above. Good point to go write the real doc and start on models; bring it back when you've got it drafted.

Scoped per game would be safer. Idk how Liquipedia and esports wiki pages handle that though.


Examined how Liquipedia structures game-specific player histories separately
Examined how Liquipedia structures game-specific player histories separately
Good context from what I found: Liquipedia doesn't really solve this with a "scope by game" field — it's structural. Each game gets its own separate wiki (liquipedia.net/valorant/..., liquipedia.net/leagueoflegends/..., etc.), so a player's own page — and its nickname history — only exists within that one game's wiki in the first place. There's no cross-game merging to worry about because the pages themselves never overlap.

Team-level history works differently and actually argues against per-game scoping: an org's "formerly known as" applies across every game they field a roster in — FUT Esports, "formerly known as Futbolist," fields rosters in League of Legends, PUBG, PUBG Mobile, VALORANT, Hearthstone, FIFA, and Wildrift, all under that one name-history, not a separate rename record per game.

That's not a perfect analogy to your case though — Liquipedia's player pages track career identity (their one competitive handle over a whole career), while your GamerTag is closer to a tournament display name a student picks per registration. Different unit of what's being tracked. Given that, per-game scoping is still the right call for you specifically — someone entering a Valorant division and a chess division in the same event isn't the same "identity" the way a pro player's handle is, and mixing an old FIFA tag into their Valorant history would just be noise. You're not really disagreeing with Liquipedia's model here, you're solving a different problem than theirs.

Practically: this stays a pure query filter (WHERE game = X), no schema change from what we already have — you're filtering the same snapshotted gamer_tag values by the Division's Game FK. Nothing to redesign, just confirms the read-side logic when you build that view later.
