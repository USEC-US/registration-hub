# Secondary Account Navigation Design

**Status:** Approved design

## Goal

Add a compact secondary navigation bar directly below the existing brand navbar. It separates public navigation from account-dependent controls while retaining the existing localized routing model.

## Layout

The existing brand/navbar remains unchanged. A second bordered bar uses the same maximum width and horizontal alignment as the page shell.

Its two compact rows are right-aligned:

1. Public navigation: `Tournaments | Rules`.
2. Account navigation and locale: either `Login | Register | language dropdown` or `Welcome, <full name> | My registrations | language dropdown`.

There is no left-side title or filler content in the secondary bar. On narrow screens, items may wrap while preserving the row order and tap targets.

## Public Navigation

- `Tournaments` retains its existing localized destination.
- `Rules` is an accessible, non-navigating visual stub until the future public rules feature and API exist. It must not point at a route that returns a 404.

## Account State and Actions

On client mount, the shell checks for an access token.

- Without a token, the second row shows localized Login and Register links.
- With a token, it loads the existing current-user endpoint. Once resolved, it replaces Login and Register with a localized Welcome link and My registrations.
- The Welcome link opens the existing Profile page. My registrations retains its existing localized destination.
- A 401 or 403 clears the stored session and falls back to the signed-out controls. A non-authentication profile-load failure must not clear the session or incorrectly present the user as signed out.
- While account state is unresolved, reserve the secondary row without announcing a misleading sign-in/redirect status.

## Localized Names and Locale Control

The welcome string is localized.

- English displays `Welcome, {first_name} {last_name}`.
- Vietnamese displays `Chào mừng, {last_name} {first_name}`. This preserves Vietnamese family/middle-name ordering; for example, `Nguyễn Hữu Quốc` and `Thắng` become `Nguyễn Hữu Quốc Thắng` in Vietnamese and `Thắng Nguyễn Hữu Quốc` in English.

Replace the present EN/VI link group with a single accessible language dropdown. It shows the active locale and navigates to the localized version of the current URL when changed, preserving the existing full-page locale-switch behavior.

## Boundaries

- Reuse the existing account API, session storage, localized href helpers, and `CurrentUser` contract.
- Do not add an account-level gamer tag, backend endpoint, persistent account cache, Rules page, or rules API.
- Do not alter tournament registration, profile form, redirect-localization behavior, or RichText/Paraglide typing.

## Tests

Add layout-level coverage for:

- public links and the Rules stub;
- signed-out Login/Register state;
- signed-in English and Vietnamese welcome-name ordering, Profile, and My registrations links;
- 401/403 fallback behavior and non-authentication error behavior;
- locale dropdown rendering and current-route localization.

Existing auth, registration, and locale-navigation tests remain outside this change unless their shell assumptions require an intentional update.
