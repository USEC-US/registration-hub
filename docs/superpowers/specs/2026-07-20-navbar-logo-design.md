# Navbar Logo Design

## Goal

Replace the decorative bracket dot to the left of the application title with the supplied tournament logo while preserving the existing navigation layout, title, kicker, localization, and home-link behavior.

## Assets

Use the three equivalent 750 by 750 pixel files already supplied in `web/static/logo/`:

- `logo.avif`
- `logo.webp`
- `logo.png`

The navbar will render them through one `<picture>` element in AVIF, WebP, then PNG fallback order. Static asset URLs will use the `/logo/` prefix.

## Presentation

The logo will occupy a fixed 48 by 48 pixel box (`h-12 w-12`) with `object-contain` and `shrink-0`. It will sit directly to the left of the existing title-and-kicker text within the home link. The old `bracket-node` element in that brand block will be removed.

The logo is decorative in this context because the adjacent localized application title already supplies the link's accessible name. The fallback `<img>` will therefore use an empty `alt` attribute and explicit intrinsic dimensions to avoid layout shift.

## Scope

Only the brand area in `AppShell.svelte` changes. Navigation destinations, responsive grid behavior, translations, page width, and content are unchanged. The existing logo files are reused without image processing.

## Verification

Add a focused test before the production edit. It will verify that the navbar brand uses the three formats in the intended fallback order, renders the 48-pixel fallback image with decorative alternative text, and no longer renders the bracket dot in the brand link. Then run the focused test, frontend checks, lint, and the complete frontend unit suite.
