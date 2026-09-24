---
name: Ditto
description: A RAG experiment bench laid out like a reference manual open at a tabbed division.
colors:
  hue-violet: "#6d4bc4"
  hue-yellow: "#f2b51b"
  hue-orange: "#e8622a"
  hue-grass: "#4e9a45"
  hue-teal: "#14908e"
  hue-ultramarine: "#2f4fb5"
  errata: "#d8321e"
  errata-ink: "#b3261a"
  ink: "#17161a"
  ink-2: "#56545c"
  ink-3: "#6e6c74"
  ink-inverse: "#ffffff"
  binder: "#e6e3dc"
  binder-2: "#efede7"
  leaf: "#fcfbf8"
  field: "#ffffff"
  line: "#dcd9d1"
  line-strong: "#8a877f"
  ok-ink: "#2b6b2f"
  pause-ink: "#8a5a12"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "46px"
    fontWeight: 750
    lineHeight: 1.02
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 75"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
    fontVariation: "'wdth' 87.5"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "'tnum' 1"
  lede:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.55
  read:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "15.5px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 650
    lineHeight: 1.3
  figure:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 750
    lineHeight: 1
    fontVariation: "'wdth' 75"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  hairline: "2px"
  leaf: "3px"
  inner-tab: "6px"
  tab: "7px"
  hole: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "28px"
  gutter: "44px"
components:
  button-primary:
    backgroundColor: "{colors.hue-violet}"
    textColor: "{colors.ink-inverse}"
    rounded: "{rounded.hairline}"
    typography: "{typography.label}"
  button-default:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.hairline}"
    typography: "{typography.label}"
  button-default-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ink-inverse}"
  button-subtle:
    textColor: "{colors.ink}"
    padding: "0 8px"
  button-subtle-hover:
    backgroundColor: "{colors.binder-2}"
  button-danger:
    backgroundColor: "{colors.field}"
    textColor: "{colors.errata-ink}"
    rounded: "{rounded.hairline}"
  button-danger-hover:
    backgroundColor: "{colors.errata}"
    textColor: "{colors.ink-inverse}"
  button-disabled:
    backgroundColor: "{colors.binder}"
    textColor: "{colors.ink-3}"
  input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.hairline}"
  input-disabled:
    backgroundColor: "{colors.binder}"
    textColor: "{colors.ink-3}"
  choice-leaf:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.leaf}"
    padding: "12px 14px 13px 12px"
  choice-leaf-disabled:
    backgroundColor: "{colors.binder}"
    textColor: "{colors.ink-3}"
  rail-tab:
    backgroundColor: "{colors.hue-violet}"
    textColor: "{colors.ink-inverse}"
    rounded: "{rounded.tab}"
    padding: "11px 14px 12px"
  leaf:
    backgroundColor: "{colors.leaf}"
    textColor: "{colors.ink}"
    rounded: "{rounded.leaf}"
  errata-slip:
    backgroundColor: "{colors.errata}"
    textColor: "{colors.ink-inverse}"
    rounded: "{rounded.hairline}"
    padding: "14px 16px"
  note:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.hairline}"
    padding: "14px 16px"
  trait:
    backgroundColor: "{colors.binder}"
    textColor: "{colors.ink}"
    rounded: "{rounded.hairline}"
    padding: "1px 7px 2px"
  task-card:
    backgroundColor: "{colors.leaf}"
    textColor: "{colors.ink}"
    rounded: "{rounded.leaf}"
    padding: "12px 12px 12px 16px"
---

# Design System: Ditto

## Overview

**Creative North Star: "The Tabbed Reference Manual"**

Ditto is a reference manual lying open at a tabbed division. Each task stage is a full-strength coloured divider board. The page you work on is a milk-acetate leaf hinged above that board, with two punch holes on its bound edge where the board shows through. The researcher always knows where they are because the hue of the board, the extended tab in the rail, and the numbered chip before the page title all say the same thing.

The system is dense but legible. It is built for long sessions reading tables and choosing among techniques, so the manual's devices do real work: booktabs rules frame every table and list, the margin column carries each section's explanation in a serif reading voice, and machine values (registry keys, prompts) are set in mono. Colour is structural. The six division hues identify stages and the current selection. Vermilion is held back for errors. Everything else is ink on paper.

The world rejects the lavender-gradient SaaS sidebar with glass cards and a mascot hero. The Ditto metaphor (the creature that takes the shape of what it studies) survives only as a light thread in the violet blob mark. It never costs clarity.

**Key Characteristics:**
- Six division hues at full strength; the current one (`--sec`) tints the board, the active tab, the primary button, checked holes, the page-number chip, and the best row.
- Near-white acetate leaf on a warm grey desk (binder), with a hairline and one short soft shadow.
- Archivo variable for everything interactive (condensed widths for headings), Source Serif 4 for explanations, JetBrains Mono for machine values.
- State is shown by physical metaphor: selected = punched hole, disabled = face-down (dashed edge, binder fill), pending = half-hinged glyph, error = vermilion errata slip.
- Motion is a 90ms two-frame step with no easing.
- UI copy is PT-BR and follows the SBB UX-writing rules adopted in PRODUCT.md.

## Colors

Six saturated divider hues on a warm paper-and-ink ground, plus one vermilion reserved for errors.

### Primary: the division boards
The primary colour is always whichever division is current, exposed as `--sec` with its text partner `--on-sec`. The shell sets `data-section` on the page and on each rail tab. No page picks a hue directly.

- **Divider Violet** (`hue-violet`): Início. On-colour is white. Also the fill of the Ditto mark in every division.
- **Chrome Yellow** (`hue-yellow`): Preparar (step 1). On-colour is ink.
- **Oxide Orange** (`hue-orange`): Experimentar (step 2). On-colour is ink.
- **Grass** (`hue-grass`): Comparar (step 3). On-colour is ink.
- **Teal** (`hue-teal`): Conversar (step 4). On-colour is ink.
- **Ultramarine** (`hue-ultramarine`): Ajustar. On-colour is white.

The best-ranked row tints to `color-mix(in srgb, var(--sec) 12%, var(--leaf))`. A filled button darkens on hover to `color-mix(in srgb, var(--sec) 84%, var(--ink))`.

### Secondary: errata
- **Errata Vermilion** (`errata`): the fill of the errata slip, the danger button's hover fill, and the border of a failed task card.
- **Errata Ink** (`errata-ink`): error text (field error messages, failed status) and the resting danger button's text and border.

### Neutral
- **Ink** (`ink`): body text, all control edges when hovered or checked, focus outlines, heavy booktabs rules (1.5px), the fill of the score bar.
- **Ink 2** (`ink-2`): secondary text such as ledes, the serif reading voice, captions, and meta lines.
- **Ink 3** (`ink-3`): placeholders, disabled text, registry keys, operators in the test strip.
- **Binder** (`binder`): the desk behind the rail. Also used for disabled fills, trait chips, user chat bubbles, and inactive inner tabs.
- **Binder 2** (`binder-2`): hover wash on rows, records, table-of-contents entries, and subtle buttons.
- **Leaf** (`leaf`): the acetate page, the test strip, task cards, assistant replies, drawers.
- **Field** (`field`): controls placed on the leaf, such as inputs, choice leaves, notes, winner card, and chat well.
- **Line** (`line`): hairline row dividers and section dividers.
- **Line Strong** (`line-strong`): resting control edges. It is chosen to reach at least 3:1 against the leaf.
- **OK Ink** (`ok-ink`) / **Pause Ink** (`pause-ink`): done and paused status text, and the "saved" confirmation.

### Named Rules
**The Errata Rule.** Vermilion appears only when something went wrong or would destroy data: the errata slip, field errors, failed status, the confirmed "Remover" button. It is never used for decoration, emphasis, or brand.

**The One Division Rule.** Each page uses exactly one hue, the one belonging to its division, taken from `--sec`. Hues from other divisions appear only on their own rail tabs and on their table-of-contents tabs on Início.

**The Structural Hue Rule.** Division hues fill surfaces such as boards, tabs, buttons, holes, chips, and badges. They are never used as text colour on the leaf.

## Typography

**Display Font:** Archivo variable (wdth 62–125, wght 400–800), with system-ui fallback
**Body Font:** Archivo for the interface; Source Serif 4 (opsz 8–60, wght 400/600), with Georgia fallback, for the reading voice
**Label/Mono Font:** JetBrains Mono (400/500), with ui-monospace fallback

**Character:** A condensed, heavy grotesk does the talking for the interface: titles, tabs, buttons, figures. A calm book serif explains what things mean, the way the prose of a manual does. Mono marks anything the machine owns.

### Hierarchy
- **Display** (750, 46px, 1.02, `wdth` 75, -0.01em, balanced wrap): the page title only. It drops to 34px at 900px and below. It is prefixed by the division-number chip when the division is a numbered step.
- **Headline** (700, 20px, 1.2, `wdth` 87.5): section headings in the margin column. Related sizes use the same setting: TOC links (19px), winner title (22px), drawer title (750, 26px, `wdth` 75).
- **Title** (650, 15px, 1.3): sub-headings, choice names, record links (15.5px), field labels (14px).
- **Body** (400, 15px, 1.5, tabular numerals everywhere): interface text, table cells (14px), table headers (650, 13px).
- **Lede / Read** (Source Serif 4, 18px / 15.5px, 1.55, `ink-2`, lede max 62ch): the page lede, section explanations (14.5px), choice descriptions (14px), field descriptions (13.5px), note bodies, empty states, assistant chat replies (16px). The lede is 16.5px at 900px and below.
- **Figure** (750, 30px, `wdth` 75, line-height 1): counts in the test strip (24px on mobile), rank numbers (22px), and the winner badge (800, 30px).
- **Mono** (JetBrains Mono, 12–13.5px): registry keys beside choice names, rail tab numbers, the page-number chip, prompt text, textareas, and placeholder tokens.

### Named Rules
**The Two Voices Rule.** If the text tells the user what something means or why, it is set in the serif. If the user acts on it or scans it, it is set in the grotesk. Machine identifiers are set in mono and always sit beside a human name, never replace it.

**The Condensed Head Rule.** Condensed widths (`wdth` 75 or 87.5) are for headings, tabs, and figures only. Body and controls stay at normal width.

## Layout

**Shell.** A two-column grid: a 236px tab rail on the binder desk, then the board. The board is a padding frame in `--sec` (14px on the top, right, and bottom; 0 on the left, where the tabs join it). It holds the leaf, which is at least viewport height minus 28px. Leaf padding is 44px on top, `clamp(24px, 4vw, 64px)` on the right, 72px at the bottom, and `clamp(56px, 5vw, 84px)` on the left, which leaves room for the two punch holes at 22% and 62% of its height. Page content is capped at 1160px, forms at 1040px, and the page head at 760px.

**Margin-column sections.** Every form and detail page is a stack of sections. Each is a two-column grid: heading plus serif explanation on the left (180–250px, or 160–220px when narrow), controls on the right. The column gap is 16px/44px and each section has 28px vertical padding. Sections are divided by a hairline, and the first one opens with a 1.5px ink rule. This is the single form pattern across pages.

**Rhythm.** Spacing steps are 4, 8, 12, 16, 28, and 44px. The page head sits 36px above the first section, choice leaves are 8px apart, and action rows use 10px gaps.

**Grids of choices.** Choice leaves auto-fill at a minimum of 230px. Filters auto-fill at 170px. Legends auto-fill at 260px.

**Responsive (900px and below).**
- The rail becomes a **3×2 grid of tabs** above the leaf. Tabs get top-rounded 7px corners and do not step sideways. The active tab is marked by a 4px inset ink bar at its foot. Sub-page lists leave the rail and reappear as a wrap of bordered links at the top of the leaf (the active one is filled with ink).
- The brand shrinks to 28px, and the subtitle and rail footer are hidden.
- The leaf gets 3px corners and 24px/16px/48px padding. **The punch holes are removed.**
- Margin-column sections collapse to one column (12px gap, 22px padding). Choice leaves become one column.
- **Tables marked for stacking become two-column cards**: rank first on its own row, then the scores (so scores never scroll away), then the combination and text cells at full width. Each cell is labelled from its `data-label`. The best row keeps its 12% hue tint.
- The test strip stops being sticky and its action goes full width. Inner tabs scroll horizontally. The winner card, agent flow, and home head collapse to one column, and the home mark is hidden.

## Elevation & Depth

The system is mostly flat paper. Depth comes from the physical stack (desk, then board, then leaf) and from ink rules, not from shadows. Two soft shadows exist, and each belongs to one role.

### Shadow Vocabulary
- **Leaf shadow** (`box-shadow: 0 1px 0 rgba(23,22,26,.05), 3px 5px 10px -4px rgba(23,22,26,.22)`): the leaf resting on its board, and the errata slip resting on the leaf.
- **Lift shadow** (`box-shadow: 0 1px 0 rgba(23,22,26,.06), 4px 10px 22px -8px rgba(23,22,26,.3)`): things that float above the page, which are dropdowns and popovers and background task cards.
- **Punched inset** (`inset 2px 3px 4px rgba(23,22,26,.55)` on the leaf's holes; `inset 1px 1px 2px rgba(23,22,26,.45)` on a checked choice hole; `inset 1px 2px 4px rgba(23,22,26,.35)` on the winner badge): shows that the board is being seen through a hole.

### Named Rules
**The Paper Stack Rule.** Only the leaf, the errata slip, and floating layers cast a shadow. Cards, choice leaves, tables, and buttons on the leaf stay flat and are separated by ink edges and hairlines.

## Shapes

Corners are nearly square, like cut paper. Controls, chips, the errata slip, notes, and pagination use a 2px radius. The leaf, choice leaves, the winner card, the chat well, and task cards use 3px. Only divider tabs are properly rounded: rail tabs are 7px on the bound side only (`7px 0 0 7px`), and inner tabs are `6px 6px 0 0`. Holes are circles (radio holes, leaf punch holes, the winner badge, status glyphs). Checkbox holes use 4px corners.

Edges carry meaning. A 1px `line-strong` edge means the control is at rest. A 1.5px ink edge means structure or emphasis (booktabs rules, buttons, the winner card, the "next step" card, task cards). A dashed edge means face-down or disabled.

## Components

### Buttons
Heavy-edged and flat, like stamped paper controls.
- **Shape:** squared-off corners (2px) with a 1.5px ink border on every variant. Label is Archivo 650, +0.005em.
- **Primary (filled):** `--sec` fill with `--on-sec` text. Hover darkens to 84% hue plus ink. The form's primary action sits bottom-right with a trailing arrow icon. On Novo experimento it lives in the sticky test strip.
- **Default / outline / light:** field fill with ink text. On hover it inverts to ink fill with white text.
- **Subtle:** no border, underlined ink text, 8px inline padding, binder-2 wash on hover. Used for "Marcar todos" and "Cancelar".
- **Danger:** field fill with errata-ink text and border. On hover it fills with errata and white text. It appears only as the second step of an inline confirmation.
- **Disabled (face-down):** binder fill, ink-3 text, dashed line-strong border, no underline.
- **Focus:** a 2px ink outline at 2px offset, set globally. Mantine's own focus ring is turned off.
- **Transition:** background and colour change over `90ms steps(2, end)`.

### Choice leaves (signature)
These are options the user can read before choosing. Each leaf shows a name, a mono registry key, an optional tag, and a serif description.
- **Style:** field fill with a 1px line-strong edge and 3px corners. An 18px "hole" sits in the left column (a circle for radios, a 4px square for checkboxes). The native input is visually hidden.
- **Hover:** the edge turns ink.
- **Checked:** ink edge plus a 1px inset ink ring. The hole is punched through, filled with `--sec` with an inset shadow, and checkboxes get an `--on-sec` tick.
- **Focus:** a 2px ink outline on the whole leaf (`:has(input:focus-visible)`).
- **Disabled:** binder fill, dashed edge, ink-3 text, not-allowed cursor.
- **Group head:** the legend (title, 14px) with a "n de m" count and a subtle "Marcar todos / Desmarcar todos" toggle.

### Inputs / Fields
- **Style:** field fill with a 1px line-strong border and 2px corners. Text is 15px and placeholders are ink-3. Textareas are set in mono at 13.5px.
- **Label and description:** a label is always present (650, 14px). An optional serif description (13.5px, ink-2) sits between the label and the field. Placeholders only show examples.
- **Hover / Focus:** the border turns ink. Focus adds a 2px ink outline at 1px offset.
- **Error:** errata-ink message, 13.5px, telling the user how to fix it.
- **Disabled:** binder fill with a dashed border and ink-3 text.
- **Dropdowns:** field fill with a 1px ink border, 3px corners, and the lift shadow. Selected options get a binder wash and hovered options a binder-2 wash.

### Navigation: tab rail
- **Rail tabs:** one divider per division, filled with its own hue. Text is Archivo 700, 16px, `wdth` 87.5, preceded by a mono step number (12px, 85% opacity; blank for Início and Ajustar). Inactive tabs are pulled 14px back into the desk. **The active tab extends to meet the board** (translateX(-14px) to none over 90ms steps(2)). This hinge is the signature interaction. Inactive tabs underline on hover.
- **Sub-pages:** only the active division shows its pages, and only when it has more than one. They are 14px/500 links. The current page is a small leaf-coloured slip (ink text, 650).
- **Inner tabs (Mantine Tabs):** they repeat the rail. Inactive tabs are binder with a line-strong edge. The active tab is a divider filled with `--sec`. The list sits on a 1.5px ink rule.
- **Back link:** ink-2, 600, with a reversed arrow. It sits above the title.
- **Mobile:** 3×2 tab grid plus sub-nav links at the top of the leaf (see Layout).

### Page head
The display title is prefixed, for numbered divisions only, by a **page-number chip**: a mono digit on a `--sec` square, rounded on the bound side (`0.25em 0 0 0.25em`), half the title's size. It has a visually hidden "Etapa n, Divisão:" for screen readers. Below it is the serif lede. A meta line can follow (ink-2, 14px) with actions aligned right.

### Notices
- **Errata slip:** vermilion fill, white text, alert icon in a 20px column, bold title, 14.5px body. It uses `role="alert"`, has 2px corners and the leaf shadow, and is at most 760px wide. It is the only place the error hue fills a surface.
- **Note:** field fill with a line-strong edge, info icon, bold title, and serif body. It uses `role="status"`.
- **Saved:** an inline check plus text in ok-ink (600, 14px), placed beside the button that saved.

### Status tag
A glyph plus a word, never colour alone. The glyph is 11px with a 1.5px currentColor edge. Labels come from the glossary.
- **Concluído** (done): filled circle, ok-ink.
- **Em andamento / Na fila** (running): half-filled circle that flips 180° in a 900ms `steps(2)` loop ("half-hinged"), ink.
- **Pausado** (paused): two vertical bars, pause-ink.
- **Falhou** (failed): filled square, errata-ink.
- **Idle / unknown:** empty circle, ink-2, showing the raw status text.

### Tables and records
- **Booktabs:** 1.5px ink rules above and below the table, a 1px ink rule under the header, and hairline rows. Headers are 650/13px and can carry a mono sub-key. Numbers are right-aligned. Clickable rows wash to binder-2. The best row is tinted with the hue at 12%.
- **Sort headers:** underline on hover. The active sort has a 2px underline.
- **Score cell:** the value to two decimals plus a 40×6px track (line) with an ink fill. The best value in a column is 750. A missing value is an ink-3 em dash.
- **Traits:** the five parts of a combination as binder chips. Each shows the dimension name (500, ink-2) and then the value (600).
- **Records:** a list framed by the same heavy rules. Each row has a 650 link and a 13.5px ink-2 sub-line and date. The whole row is clickable with a binder-2 wash.
- **Caption and legend:** "Tabela n." captions and a definition-list legend with the metric name (650) and its serif meaning.

### Winner card
The top result, set like a figure in a manual. It has a field fill, a 1.5px ink edge, and 3px corners. A 64px `--sec` circle badge holds the rank in condensed 800. Next to it are a condensed title, trait chips, and headline metrics (values at 17px).

### Test strip
This shows the cost of a run before the user commits. It is sticky at the bottom of the leaf, uses the leaf fill, and sits on a 1.5px ink rule. It reads as a condensed-figure formula ("48 combinações × 2 perguntas = 96 respostas · cerca de 36m 47s"). The primary action is at the right. If something is missing, the strip lists it in a line below and the action is shown face-down.

### Task cards
Background jobs stack bottom-right, at most 360px wide. Each card has a leaf fill, a 1.5px ink edge (errata when failed), the lift shadow, and enters with the 90ms hinge. It shows the kind (12.5px, ink-2), a one-line label, a status tag, and a message. On the right are a close button (hidden while running) and an "Abrir" link.

### Chat
The chat well has a field fill with a line-strong edge. User turns are on the right in binder bubbles. Assistant turns are on the left in serif, 16px, on leaf with a hairline. The speaker name is 650/12.5px. The composer is an input grid with the send button beside it.

### Motion
There is one motion token: `90ms steps(2, end)`, with no easing curves. It drives the tab hinge, button colour, input and choice edges, the page hinge on route change (opacity 0.35 plus `rotateY(3deg)` from the left edge, down to rest), task-card entry, and the drawer. The running glyph is the only looping motion. `prefers-reduced-motion` reduces all of it to 0.01ms.

### UX writing (PT-BR, from the SBB rules)
- Sentence case everywhere: "Novo experimento", "Gerar experimento", "Configurações de chat".
- Buttons are 1–4 word actions: "Gerar experimento", "Exportar CSV", "Marcar todos", "Remover", "Abrir".
- Every field has a visible label. Placeholders only show examples.
- Errors say how to fix the problem. Thrown errors are shown without the "Error:" prefix.
- Destructive actions are confirmed inline: "Remover" is replaced in place by "Remover de vez?" with a danger "Remover" and a subtle "Cancelar".
- Step labels are nouns (Preparar, Experimentar, Comparar, Conversar). Technique and metric names come from the glossary in plain PT-BR, with the registry key in mono beside them.
- Empty states teach the next step in the serif voice and include the action that gets there.

## Do's and Don'ts

### Do:
- **Do** take every accent from `--sec` / `--on-sec` so a page automatically carries its division's hue. Add a new route to the right division in `sections.ts` rather than choosing a colour.
- **Do** lay forms out as margin-column sections: heading and serif explanation on the left, controls on the right, and a 1.5px ink rule opening the first section.
- **Do** present options users must understand as choice leaves (name, mono key, serif description), not as bare checkboxes or multiselects.
- **Do** show status as glyph plus word through the status tag. Colour is only a third, redundant signal.
- **Do** frame every table and record list with 1.5px ink rules and hairline rows, right-align numbers, and use tabular numerals.
- **Do** use `90ms steps(2, end)` for every transition and animation, and respect reduced motion.
- **Do** show the cost of a run (combinations × questions, estimated time) before the primary action that starts it.
- **Do** confirm destructive actions inline next to the trigger, with a danger button and a "Cancelar".
- **Do** keep a 2px ink focus outline visible on every interactive element, including whole choice leaves and sort headers.

### Don't:
- **Don't** use vermilion (`errata`, `errata-ink`) for anything except errors, failures, and confirmed destruction.
- **Don't** use a hue from another division on a page, or use any division hue as text colour on the leaf.
- **Don't** use eased or springy motion (ease-in-out, cubic-bezier, framer-motion springs). Ditto's motion is stepped.
- **Don't** build the lavender-gradient SaaS look: glass cards, blurred backdrops, soft colour gradients, or a mascot hero.
- **Don't** add shadows to cards, choice leaves, tables, or buttons on the leaf. Shadows belong to the leaf, the errata slip, and floating layers.
- **Don't** put uppercase eyebrows or kickers above page or section titles. The division-number chip is the only prefix a title takes.
- **Don't** use placeholders as labels, or title case in UI copy.
- **Don't** show a registry key (`naive`, `mmr`) without its plain-language name beside it.
- **Don't** keep punch holes or the stepped rail offset at 900px and below. The narrow layout is a 3×2 tab grid on a flat leaf.
