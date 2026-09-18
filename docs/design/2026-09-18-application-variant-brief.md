# The applications wear the site's squared system, in its "Ledger" weight

Date: 2026-09-18. Status: decided (Lorenzo, 2026-09-18: «a e la dark mode per ora
togliamola»). Tracker: REB-298, first card of Shared UI v1; REB-299 to REB-302
implement it.

## 0. Why

Lorenzo, 2026-09-17: «entrambi gli applicativi devono arrivare ad avere la stessa ui
che c'è nel sito attualmente, adattata al fatto che devono essere applicativi
funzionali quindi sicuramente alleggerita, ma con quello stile squadrato e gli stessi
font e colori».

The site (`projects/website/src/landing.css`, `system.css`) is zero radius, 2px ink
borders, an 8px step shadow with no blur (`--landing-step`), a 16px grid
(`--system-cell`), Outfit 300 to 600. The CRM's `apps/web/src/styles/tokens.css` is
`--radius: 10px` with blurred shadows, and `docs/design/DECISIONS.md` said so on purpose
(ORB-73, 2026-09-10: public pages squared, applications rounded). The hub copies the
CRM's tokens and adds a `.site` scope for its public pages only. This record moves that
line: the applications follow the site, one step lighter.

## 1. The brief

| | |
|---|---|
| Subject | The application variant of letsrebase.com's squared system, worn by PigroCRM (`/app`) and by the hub (admin section and member area): dense working screens, not a landing. |
| Audience | An Italian freelancer running customers, deals, invoices and hours in PigroCRM; a rebase admin scanning talents and companies; a member editing their own card. All of them arrive from the site and already know its look. |
| The job | Read a list, fill a form, act in a dialog, and never doubt it is the same product as the site, while spending less ink than the landing. |
| Palette | The six colours of `shared/brand/palette.css` and nothing else: Paper ground, Prussian Blue ink, borders and sidebar, Charcoal Blue quiet text, Watermelon Strong primary action, Watermelon focus ring and kicker tile, Royal Gold accent on dark grounds only. Tints by `color-mix`, never a seventh hex. |
| Type | Outfit only, via `@rebase/brand/font.css`: body 300/400, labels and titles 500, kickers 600 with 0.12em tracking; tabular numerals in every column of figures. |
| Density | Middle in lists (48px rows, 14px cells, 24px page titles), compact in forms (two columns, label beside field, action bar bottom right). |
| Signature | The step shadow: an ink offset with no blur, on what floats and on nothing that sits in the page. |
| States | Empty (one sentence and the one action), loading (skeleton shaped like the row), error (what happened and the remedy), long content (Italian labels 20% longer than English, a 60-character company name in a cell). |
| Constraints | Tailwind v4 `@theme` tokens, radix primitives with CVA, the 16px grid, no new colours; the website is the reference and is not touched. |
| Non-goals | No restyle of the website. No new palette entry, no second typeface, no radius above zero anywhere. Deviations from the taste profile, on purpose: Outfit instead of Inter (the repo's decision), step shadows instead of "no shadows" and radius 0 instead of 2 to 8px (the site's signature, asked for by name). |

## 2. The two options, drawn on the same four screens

Canvas: Claude Design project "Rebase application variant"
(`https://claude.ai/design/p/995274a6-c9ae-4a58-9a71-d66539f98876`), built on the
"rebase Design System" project synced from this repository. Eight artboards at
1440×900, two rows of four: PigroCRM `Fatture` list, PigroCRM `Nuovo cliente` form,
hub admin `Talenti` list, hub member area `La mia scheda` with the edit dialog open.
The data is invented, in Italian, in the formats the routes use; no real client name is
on it. The rendered export is `application-variant/contact-sheet.png`, and the
screen map the export wrote, artboard by repo file, is `application-variant/screen-map.md`.
The canvas is not a source of truth: the implementation reads this record and the
decision rows, never the export's CSS.

**Option A, "Ledger".** Borders 1px full-strength ink on cards, tables and controls, the
site's 2px kept on the primary button and the focus ring. Step shadow 4px (half
`--landing-step`) on floating surfaces only: dialog, menu, popover, toast. The 16px grid
ground kept at 4% ink behind the content area. Tables ruled: column separators, a 2px
rule under the header, no zebra. Sidebar Prussian Blue with Paper text and a
Watermelon Strong tile beside the active item. Badges outlined with ink text, a tint
only for the semantic states.

**Option B, "Paper".** Borders 2px ink on cards and controls, as on the site; 1px only
for table rows. Step shadow 6px on cards and on floating surfaces, the value the site's
`.card` uses. No grid ground inside the app. Tables zebra on Paper, no column
separators. Sidebar Paper-white with ink text, a 2px ink right border, the active item a
filled ink box. Badges filled with a tint.

Recommended A, and A was chosen. B at 2px and 6px on every card reads as the landing
with more content in it; A keeps the site's signature (ink, squared, step shadow) at the
weight a working screen can carry. Both are squared like the hub's `.site` scope, which
holds the site's own 2px and 6px; A lightens those weights for dense screens.

## 3. The decisions, one paragraph each

**Shape.** Radius zero across the whole derived scale, in both applications, by
default: the `.site` scope stops being a scope and becomes the tokens. Borders 1px ink
(`--color-prussian-blue` at full strength) on cards, inputs, tables and controls; 2px
only on the primary button and the focus ring, which is where the site's weight stays
visible.

**Shadow.** One offset, `--step: 4px`, ink-coloured, no blur, on floating surfaces only
(dialog, sheet, dropdown, popover, tooltip, toast). A card, a table, a page header sits
on the page with a border and no shadow. The site keeps its 8px and 6px; the app never
uses them.

**Ground.** The 16px grid behind the content area, the site's `--system-cell`, at 4%
ink where the site draws it at 7% (`system.css:12`): the same paper, one shade lighter,
so a dense page does not fight its own ground. A card is opaque Paper white over it.

**Tables.** Ruled: 1px column separators, a 2px rule under the header, 48px rows, no
zebra, figures right-aligned in tabular numerals, a long cell ellipsised with the full
value on hover.

**Sidebar.** Prussian Blue with Paper text, the active item marked by a Watermelon
Strong tile beside it, in both applications. The CRM's menu is already this; the hub's
admin nav adopts it.

**Badges and states.** Outlined boxes with ink text by default; a tint (by `color-mix`
of the semantic hue) only for the semantic states, so the primary action stays the
one saturated thing on a screen.

**Dark mode.** Dropped. The CRM's `.dark` block in `tokens.css` goes with REB-299,
together with every assertion in `tokens.test.ts` that reads it: "defines a dark mode",
the `block('.dark')` cases on `--border`, `--input` and the sidebar tokens, the
`[':root', '.dark']` loop and the contrast pair on the dark ground. The hub's own
`tokens.test.ts` asserts `@custom-variant dark (&:is(.dark *));` in a `tokens.css` that
REB-302 deletes, so that assertion goes there. Nothing sets the class today, and a second
palette would have to be kept honest against every rule above for no reader. It can
come back as its own brief when somebody asks for it.

## 4. Where the values live

`@rebase/ui` (`shared/ui`, REB-299) declares the semantic slots once, squared by
default; both applications import it and delete their own `tokens.css`. The primitives
follow in REB-300, the contract test that proves the two apps and the site agree in
REB-301, and the hub's member and admin areas move onto it in REB-302, after REB-279.
Every value above is a token; a raw hex, px or shadow typed into a component is a
defect even when it looks right.
