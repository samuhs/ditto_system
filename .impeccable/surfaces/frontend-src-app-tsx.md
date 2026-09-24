---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/pages"]
---

# Ditto app shell (all routes)

Scope: the whole Ditto web app (every route under frontend/src/pages plus shell). Mode: Operate.
Audience/job: external researchers, unaided, going documents → experiment → ranked comparison → conversation. Must be neither dense-for-beginners nor shallow-for-experts; not generic SaaS; keep Ditto's personality (name + shape-shifting metaphor).
Constraints: same API and routes; navigation regrouped by task; pages may change structure (choice cards, previews, teaching empty states). SBB principles + UX writing (sentence case, 1–4 word action buttons, labels always, fixable errors, confirm destructive). WCAG 2.2 AA.

## Direction contract

THESIS: Ditto is a reference manual lying open at a tabbed division. Each task stage is a coloured divider; the page is a milk-acetate leaf hinged above it. Refuses the lavender-gradient SaaS sidebar with glass cards and a mascot hero.

OWN-WORLD: Section boards at full strength: violet (Início), chrome yellow (Preparar), oxide orange (Experimentar), grass (Comparar), teal (Conversar), ultramarine (Ajustar); vermilion held out for errata/errors only. Leaves are near-white acetate with a hairline edge, two punch holes on the bound edge, one short hard shadow. Grotesk (Archivo, condensed width for heads) for everything interactive, serif (Source Serif 4) for the manual's explanatory voice, mono (JetBrains Mono) for machine values. Selected = punched hole; disabled = face-down; pending = half-hinged; error = vermilion errata slip. Motion: 90ms steps(2), no easing.

STORY: The researcher always knows which division they are in (hue + tab), reads what each choice means right beside it, sees what a run will cost before committing, and reads rankings they can trust.

FIRST VIEWPORT: Left: stepped tab rail, one tab per division, current tab extended and tinting a 12px board margin framing the leaf. Leaf top: division number + condensed title + serif lede. Below: sections with heading/explanation in a left margin column and controls on the right. Primary action bottom-right of the form in the division hue with an arrow; Novo experimento shows a live "test strip" (formas × perguntas, tempo estimado) beside it.

FORM: challenger "Manual com abas" (rw-manual-acetate-tab-board), chosen by user over assigned list item 7; seed key c76c1123. Signature interaction: the tab-rail hinge (current tab extends into the board in a 90ms two-step).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
