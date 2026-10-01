# SplitStay: Design, Motion and Flow Guide (for the next AI agent)

You cannot see this product, so this file describes it: what it should feel like, which animations exist, how each one is built, how the user moves through it, and the traps that cost time. Read it fully before changing anything visual. It deliberately contains **no colour palette**: colours are semantic tokens in `tailwind.config.js` and `static_src/input.css`. Reuse the tokens; never hard-code colours.

---

## 1. The feeling to protect

SplitStay moves real money for groups of people who trust each other. The design must feel **calm, mature, precise**, like a serious Nigerian cooperative bank, not a fintech demo and not a Tailwind template.

Principles, in priority order:

1. **Every animation communicates state.** If a motion does not tell the user something (a payment landed, a level rose, a document was issued, something is loading), delete it.
2. **Motion is physical, not robotic.** Things overshoot slightly and settle, like liquid or a spring. Never use plain `linear` or default `ease` for meaningful movement (the only linear motion is a continuous drift such as a wave or marquee).
3. **Reveal in reading order.** Content arrives top to bottom, left to right, with small staggers, so the eye is led and never surprised.
4. **Quiet by default, expressive at moments of trust.** Page transitions, hovers and menus are subtle and fast (120 to 300 ms). The big motion is saved for three moments: the pot filling, a payment confirmed, a receipt issued.
5. **Information survives without motion.** Reduced-motion users and no-JS users must still get every fact (see section 9).
6. **No toys.** No emoji, no icon fonts, no mascots, no cartoon illustrations, no stock Lottie or AOS-style presets, no generic spinners. Icons are inline **Lucide outline SVGs at a uniform 1.5 stroke** via the `{% icon "name" size "css" %}` tag in `apps/web/templatetags/cp.py`.
7. **Typography carries hierarchy.** One sans-serif family. Distinct steps for page title, section title, body, small metadata, and tabular figures for money (`tnum`, `.amount`).

Dark mode is class-based, toggled in the nav, remembered in `localStorage`, and follows the system on first visit. Landing bands that must always be dark use `.force-dark`, which re-scopes the same tokens on one section.

---

## 2. Stack and file map

Django templates + Tailwind 3 (with `tailwind.config.js`) + Alpine.js + HTMX. No SPA, no React. React-style motion is reproduced with CSS transitions/keyframes and small vanilla JS.

| Concern | File |
|---|---|
| Tokens, components, **all animation CSS** | `static_src/input.css` (compiled to `static/css/app.css` by `npm run build:css`; the compiled file is committed) |
| Design tokens / type scale | `tailwind.config.js` |
| Shared behaviour: theme, boot screen, busy overlay, pot fill, count-ups, live-update hooks | `static/js/app.js` |
| Landing/public-page motion: reveals, word split, spotlight, magnetic, story stage, hero demo loop, scroll-spy | `static/js/landing.js` |
| Layout shell, header, footer, confirm dialog, toasts | `templates/base.html` |
| Landing | `templates/landing.html` |
| Public pages | `templates/guide.html`, `templates/partials/guide.html`, `templates/pages/*.html` |
| The live group page | `templates/groups/detail.html` + partials `_pot`, `_actions`, `_members`, `_ledger`, `_entry`, `_live`, `_status_badge`, `_header_actions` |
| Payment confirmation | `templates/payments/_confirmation_card.html` |
| Receipt | `templates/groups/_receipt_body.html` |
| Icons, money filters, badges, logo mark | `apps/web/templatetags/cp.py` |
| Views (call the same service layer as the REST API) | `apps/web/views.py` |

After any change to a template class or `input.css`, **rebuild the CSS** (`npm run build:css`). Tailwind only emits classes it finds in `templates/**`, `apps/**/*.py` and `static/js/**`.

---

## 3. The motion language (reuse these, do not invent new curves)

**Easing**
- *Spring overshoot* (liquids, level changes, tab pills, chips): `cubic-bezier(.34, 1.3, .5, 1)` or `cubic-bezier(.3, 1.25, .4, 1)`. The curve goes past 1, so the element overshoots and settles.
- *Soft spring entrance* (reveals, panels, stage layers): `cubic-bezier(.2, .9, .25, 1.1)`.
- *Calm ease-out* (draws, simple fades): `ease-out`.
- Continuous drift only: `linear`, infinite.

**Durations**
- Hover, press, menu, modal: 120 to 200 ms.
- Page entry (`.page-enter` on `<main>`): 280 ms, 6 px rise.
- Scroll reveals: 700 to 900 ms.
- Pot level change: 1.7 s. Count-up numbers: 1.3 to 1.4 s.
- Stagger step: 70 ms per item (`calc(var(--i) * 70ms)`).

**Reveal primitive (`.reveal`)**: starts at `opacity 0`, `translateY(22px)`, `blur(8px)`; when `.in` is added it resolves to its place with the spring curve. An `IntersectionObserver` adds `.in` once. Delay is set per element with `style="--d:150ms"`. Headlines use `.words`: JS splits the text into `<span class="w" style="--i:n">` and each word un-blurs 70 ms after the previous.

Both must have a no-JS fallback: the `<noscript><style>` block in each public page forces `.reveal` visible, and `.words .w` only exists after JS runs, so plain text shows without it.

---

## 4. The signature animations, one by one

### 4.1 The pot filling (the most important animation in the product)

The metaphor: a group fills a shared vessel toward a target. It must feel like liquid, not a progress bar.

Structure (`templates/groups/_pot.html`):
```
.pot > .pot-vessel (rounded, overflow hidden)
         > .pot-liquid#pot-liquid   <- this moves
              > two <svg class="pot-wave a|b"> (wave surface, drifting)
              > .pot-body (the fill block)
         > .pot-ticks (25/50/75% marks; a tick turns light once the liquid passes it)
         > .pot-sheen (soft highlight)
```
How it works:
- `.pot-liquid` is `position:absolute; inset:0` and is moved with `transform: translateY(N%)`, where `N = 100 - percent`. Percent is relative to the element's own height, which equals the vessel, so `translateY(0%)` is full and `translateY(100%)` is empty.
- It has `transition: transform 1.7s cubic-bezier(.34, 1.28, .5, 1)`. The overshoot makes it rise slightly past the target and settle.
- The wave is an SVG path with two periods; the SVG is `width:200%` and animates `translateX(-50%)` forever (`@keyframes wave-drift`), which loops seamlessly because the path repeats every half width. Two waves at different speeds, opacity and direction (`.a` 7 s, `.b` 11 s reverse) give a calm surface.
- When the level **increases**, JS adds the class `rising` to `#pot` for about 2.4 s; `.rising .pot-wave.a/.b` shorten their duration so the surface "stirs" faster, then calms.
- First page load: markup renders **empty** (`data-translate="22.2"` and default `translateY(100%)`), and JS fills it on the `cp:ready` event (after the boot screen leaves), using two nested `requestAnimationFrame` calls so the empty state paints first. Without this the animation plays invisibly behind the loader.
- Numbers count up in step (`data-count-to`, `data-count-key`): `app.js` tweens from the last known value (stored per key) to the new one with cubic ease-out.

### 4.2 Live updates without reloading (HTMX out-of-band panels)

The group page polls `GET /groups/<id>/live/` every 5 s (`hx-trigger="every 5s [document.visibilityState=='visible']" hx-swap="none"`, marked `data-quiet` so it never triggers the loading overlay). The response contains **six panels**, each with `hx-swap-oob="true"` and a stable `id`: `status-badge`, `header-actions`, `pot`, `actions`, `members`, `ledger`.

Critical details:
- **Same `id` on old and new element is what makes CSS transitions survive a swap.** HTMX copies the old element's attributes onto the new one, then applies the new attributes after a short settle delay, so the liquid transitions from old to new level instead of restarting. Never swap the pot by replacing a parent without ids.
- In the swapped markup the liquid's style must carry the **final** value (`style="transform: translateY(0%)"`). Only the first full-page render uses the empty-then-fill trick (`initial` flag in the view context).
- Do not put open forms or modals inside swapped panels (typing would be wiped). Dialogs live outside, and panel buttons open them with `@click="$dispatch('confirm', {...})"` or `'edit-share'`.
- New ledger rows get `.is-new` (slide in from above, background flash that fades) by comparing `data-entry` ids against a set of ids already seen. A member who becomes Paid gets `.state-flip` (small scale settle).

### 4.3 Payment confirmation: a tick that draws itself

`templates/payments/_confirmation_card.html`. An SVG circle and a check path both use `pathLength="1"`, `stroke-dasharray: 1`, `stroke-dashoffset: 1`, then animate `stroke-dashoffset` to 0:
- ring: 0.65 s starting at 0.1 s; tick: 0.42 s starting at 0.7 s; a soft glow ring expands and fades at 0.95 s.
- Everything below the tick (`.confirm-rise > *`) fades up in sequence from 1.0 s using `nth-child` delays. **Gotcha:** the last child (the button) needs its own delay entry or it appears before the tick finishes. Keep the delays list at least as long as the number of children.
- Tone: brief and confident, no confetti, no bounce. It is not a game.
- While the gateway is still confirming, the card shows the logo mark in a looping "breathing" state and polls itself (`hx-trigger="every 3s"`, `hx-swap="outerHTML"`); when status flips to paid, the same swap brings in the tick card. Failure shows a plain explanation and a way back.

### 4.4 The receipt resolving into view

`templates/groups/_receipt_body.html`. It must feel like a real document being issued.
- The paper animates `clip-path: inset(0 0 100% 0)` to `inset(0)` over 1.15 s, so it "prints" top to bottom.
- Each line has class `receipt-line` and `style="--i:N"`, fading up at `0.25s + N * 70ms`.
- The bottom edge is torn/perforated with a CSS mask: `conic-gradient(from -45deg at bottom, #0000, #000 1deg 89deg, #0000 90deg) 50% / 16px 100%`. **Gotcha:** an inverted gradient hides the entire receipt; always check visually.
- A rounded-square seal draws itself (stroke-dash trick again) at about 1.35 s, followed by the word "Paid".
- Money lines use tabular figures; the fee is its own line; electricity shows a monospace token with a copy button; the contribution list shows who paid what.
- `@media print` removes the nav/footer/animations/mask so it prints as a clean document.
- If the payout is still pending the page shows the looping logo and polls every 4 s; when it completes, the receipt animation plays as it is swapped in.

### 4.5 Loading screen and busy state (logo mark)

The mark is a rounded square (a vessel) with liquid inside, rendered inline by `{% logo_mark "unique-id" size %}` (unique id per instance because of `clipPath`). It is **static everywhere** (nav, footer, receipt) and animated only inside loaders (a past bug: the nav logo replayed its intro on every page).
- **Boot screen (`#boot`)**: outline draws (0.7 s), liquid rises with overshoot (starts 0.45 s), the wordmark fades in while its letter-spacing settles. Minimum visible time about 0.95 s, then it fades out and fires `cp:ready`, which starts the pot fill, count-ups and landing reveals.
- It plays on the **first visit of a session and on every browser reload**, and is skipped on in-app link navigation. A tiny inline script in `<head>` decides before first paint using `performance.getEntriesByType('navigation')[0].type === 'reload'` and a `sessionStorage` flag, adding class `booted` to `<html>` to hide it.
- **Busy overlay (`#busy`)**: same mark, liquid gently breathing (`alternate` infinite). It appears only if a request or a `form[data-busy]` submit takes longer than about 550 ms, so fast actions never flash it. HTMX polling is exempt via `data-quiet`.
- Never use a generic spinner.

### 4.6 Landing page motion

All in `static/js/landing.js` plus the "landing page" block of `input.css`.

- **Hero live demo**: a framed product card that plays a loop of about 16 s using the real pot component: four members flip from "Not yet paid" to "Paid" one after another (at roughly 1.3 s, 3.6 s, 5.7 s, 7.8 s), each adding a ledger line, raising the pot and counting up the total; at about 8.9 s the status becomes "Paid out" and a floating card announces the transfer with the fee; it then resets and repeats. It pauses on tab hide, starts after `cp:ready`, and shows the final state statically under reduced motion.
- **Hero atmosphere**: a faint grid that fades out with a mask, and a soft glow that follows the cursor (CSS variables `--hx/--hy` set on `pointermove`).
- **Marquee**: what you can pay (rent, electricity companies, family upkeep...), duplicated list translating `-50%` forever, edge-faded with a mask, pauses on hover.
- **Sticky-scroll story (three chapters)**: text chapters on the left scroll normally while a stage on the right stays `position: sticky`. An `IntersectionObserver` (`rootMargin: -42% 0 -42% 0`) marks the chapter in the middle of the screen as active, sets `data-active` on the stage, and layers cross-fade with a soft spring (opacity, small scale, blur). A thin rail on the left fills by thirds. Chapter 1 shows a duotone photo with a slow Ken Burns zoom plus a bank-transfer receipt card; chapter 2 a photo plus an electricity token that **types itself** with a blinking caret each time it becomes active; chapter 3 shows a ring plus month chips that cycle (`.month-chip.on` lifts and scales with overshoot) and share bars that grow. On mobile the stage is hidden and each chapter shows its own inline photo.
- **Photos**: tinted into the palette with a CSS duotone (`grayscale` + a multiply gradient). Keep them honest and licensed: only use images that genuinely show what the caption claims, and credit them (the current two are CC BY-SA from Wikimedia Commons, credited in the page footer).
- **Spotlight cards (`.spot`)**: a radial highlight follows the pointer inside the card (`--mx/--my`) and the card lifts 3 px on hover with a spring.
- **Magnetic buttons (`[data-magnetic]`)**: the button drifts toward the cursor up to a few pixels and springs back on leave. Disabled under reduced motion.
- **Feature micro-scenes**: each card demonstrates its claim. Share bars grow to their widths when the card reveals (CSS: `.reveal.in .share-bar > i`), a dashed SVG line flows from the pot to the "landlord" and "disco" boxes (`stroke-dashoffset` loop), the fee line has a gently pulsing dot, the recurring card has a ring that fills and empties, the reminder icon rings a bell every few seconds.
- **How it works tabs (Alpine)**: four equal tabs with one **sliding pill** whose `transform: translateX(tab * 100%)` uses the spring curve; panels enter with rise + un-blur; a progress bar underneath advances in quarters.
- **Facts row**: numbers count up when scrolled into view.
- **Table-of-contents scroll-spy** on the guide: the entry for the section in view gets a coloured left border and nudges 4 px right.
- **FAQ**: native `<details>`; the chevron rotates with the spring curve and the answer fades in.

### 4.7 Small, constant micro-interactions

Buttons and rows: colour transitions of 150 ms. Menus and modals: 120 to 150 ms fade/rise via Alpine `x-transition`. Toasts: slide down, auto-dismiss at 7 s. Inputs: focus ring grows with a short transition. Nothing else moves.

---

## 5. The user flow (keep this journey intact)

1. **Landing** `/`: story and live demo, CTA "Start a group". Signed-in visitors are redirected to the dashboard.
2. **Register** `/register/` (name, email, optional phone, password) or **Sign in** `/login/` (email or phone).
3. **Dashboard** `/dashboard/`: three stats, invitations (Join/Decline), "Waiting on you" with direct Pay buttons, group cards with thin progress bars that grow on load, recent activity.
4. **New group** `/groups/new/`: purpose cards, details, repeat option, destination (bank transfer or electricity bill with a live "Check this meter" result), early-payout checkbox, member rows with optional custom shares. A sticky **summary** panel updates as you type: target, headcount, equal share, service fee, and what the bill or landlord will receive.
5. **Group page** `/groups/<id>/`: the pot, "Your part" (share, paid, outstanding, Pay button), who has paid, ledger, where the money goes. Updates live (section 4.2).
6. **Pay**: POST to the group, redirect to the gateway (Paystack) or the sandbox checkout, return to the confirmation page (section 4.3).
7. **Payout**: automatic when the pot reaches the target (or the admin pays out early if allowed); status shown in "Your part"; **View receipt** (section 4.4).
8. Supporting pages, each on its own URL and **not** crammed into the landing page: `/guide/` (detailed beginner guide), `/about/`, `/fees/`, `/contact/`, `/privacy/`, `/terms/`, plus a footer linking them all and a header nav for visitors.

Rules baked into the flow (do not break them): members only pay their own share; membership and shares lock after the first payment; fees are always an explicit line; a group's total is always summed from confirmed contributions, never stored; every member (not just the admin) can read the ledger.

---

## 6. Interaction architecture (how pieces talk)

- **One confirm dialog for everything destructive** lives in `base.html`. Any button opens it with `@click="$dispatch('confirm', { action, title, body, confirmLabel, danger })"`. It POSTs a CSRF-protected form to `action`.
- **Alpine** holds UI state only (menus, modals, tabs, the group form's preview). **HTMX** replaces fragments (live panels, bell, confirmation polling, meter check, receipt polling). **Vanilla JS** is used only where timing control is needed (boot screen, pot fill, count-up, story stage, hero loop).
- HTMX CSRF: `hx-headers='{"X-CSRFToken": "..."}'` on `<body>`.
- Notification bell: badge and list refresh via out-of-band swaps every 30 s; opening one marks it read and redirects to the group.

---

## 7. Mobile is a first-class screen

Test at **320, 375, 414 and 768 px**. Rules that fixed real bugs:
- Grid and flex children that contain wide content need `min-w-0` (we use `[&>*]:min-w-0` on grids). Without it a grid column refuses to shrink and the whole page scrolls sideways.
- Wrap tables in `overflow-x-auto`, tighten cell padding on small screens, use `whitespace-nowrap` for money.
- Big amounts shrink on phones (`text-[1.5rem] sm:text-figure`); the pot narrows below 400 px and its stats stack to one column.
- Header right cluster: smaller gaps and no chevron below `sm`, so nothing spills at 320 px.
- Stickies and side-by-side stages collapse: the landing story stage is desktop only; the group page puts the right column below.
- Touch targets stay at least about 36 px.

**How to verify (do not skip):** run the app, then use a headless browser (Playwright) to load every page at each width and assert `document.documentElement.scrollWidth <= clientWidth`, listing offenders by bounding box (ignore elements clipped by an `overflow:hidden` ancestor, fixed overlays and the marquee). Also take screenshots of long pages and **look at them**. Automated tests cannot see an invisible receipt or a misplaced element.

---

## 8. Landing and content design

- Headline is a human sentence, not a feature list ("Nobody chases anybody for money."). Copy is plain, specific and Nigerian-context (rent, NEPA and electricity companies, ajo/esusu, naira and kobo).
- Dark bands (hero, features, final call to action) alternate with light bands (story, how it works, facts) for rhythm.
- Every claim has a demonstration next to it (a small live scene) instead of an illustration.
- Stats must be true statements about the product (12 electricity companies, exact-to-the-kobo splits, 100% of entries visible to members, 5-second live updates). Never invent user counts or testimonials.
- The beginner guide uses the exact button labels from the app, numbered steps, tip callouts and a glossary, so a first-time student can follow it.
- Legal pages are drafts: a lawyer must review them before launch.

---

## 9. Accessibility, reduced motion, no-JS

- `@media (prefers-reduced-motion: reduce)` shortens animations to nothing, sets stroke draws to their final state, shows all reveal content, hides extra story layers and shows the hero demo in its final state. The information is always present.
- Skip link, visible `:focus-visible` rings, `aria-live` on status text and toasts, `role="alertdialog"` on confirmation, labels on every icon-only button, `aria-current` on the active nav link, `aria-selected` on tabs.
- No-JS: reveals are forced visible by `<noscript>`, forms work as plain POSTs, pages are server-rendered.

---

## 10. Pitfalls we already hit (save yourself the time)

1. **Tailwind name collision:** a font-size called `body` and a colour called `body` both make `text-body`. The colour token is `fg` (`text-fg`).
2. **Template caching:** the dev server run with `--noreload` caches templates. Restart it after editing templates.
3. **CSS rebuild:** new utility classes do nothing until `npm run build:css`. Commit the compiled `static/css/app.css`.
4. **HTMX transition trick** needs matching ids and final-state markup (section 4.2). Replacing the pot's parent breaks the animation.
5. **`on_commit` and tests:** Celery tasks are scheduled with `transaction.on_commit`; in Django `TestCase` they only run inside `captureOnCommitCallbacks(execute=True)`.
6. **Do not animate the nav logo** on every page; only loaders animate the mark.
7. **Delay lists must cover every child** (the confirmation button appeared early once).
8. **Inverted masks hide content silently.** Look at screenshots.
9. **Never cover the pot animation with the loader.** Start it on `cp:ready`, not on `DOMContentLoaded`.
10. **Photo honesty:** a "Lagos night" image turned out to be Lagos, Portugal. Verify location and licence before using any photo, and credit it.
11. **Fixed-position cloaked overlays** (modals with `x-cloak`) can look like overflow in audits; exclude them when measuring.

---

## 11. Recommended build order for a fresh agent

1. Tokens, type scale, base layout, theme toggle and boot/busy loaders.
2. Core components (buttons, cards, inputs, badges, alerts, menus) and the icon tag.
3. Auth pages and dashboard.
4. Group create form with the live summary.
5. **Group page and the pot** (build the pot and its live panels first; it sets the quality bar).
6. Payment confirmation and receipt animations.
7. Landing page (hero demo loop, story stage, features), then the guide and the other public pages and footer.
8. Mobile audit at four widths, dark-mode pass, reduced-motion pass, print check.
9. Run the full test suite, then look at real screenshots before declaring done.

## 12. Definition of done for any visual change

- Looks right in light and dark mode, at 320 to 1280 px, with no horizontal scroll.
- The motion has a reason, uses the shared curves and durations, and degrades under reduced motion.
- No new colours or icon styles outside the tokens and the Lucide set.
- CSS rebuilt and committed; templates restarted; tests pass; screenshots reviewed by eye.
