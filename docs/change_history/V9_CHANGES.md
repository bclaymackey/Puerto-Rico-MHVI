# MHVI Dashboard — V9 change log

Source documents: `Usability study exercise 1.docx`, `Usability study
Exercise 2.docx`, `Usability study Exercise 3.docx` (GRA folder).
Scope of this pass: **the remaining Exercise 1 recommendations + all of
Exercise 2.** Exercise 3 is not implemented here — see Part 4.

Companion document: `V8_CHANGES_AND_REVIEW.md`, which covers the first five
changes and the code review of V7.

Every change in the code carries a tag naming the document and item it comes
from, e.g. `[E1-R2]` = Exercise 1, Recommended improvement 2;
`[E2-O1]` = Exercise 2, "Some other suggestions" item 1;
`[E1-I9]` = Exercise 1, Usability issue 9.

---

## Part 1 — Exercise 1: the first five (delivered in V8)

These are listed for completeness; the detail is in `V8_CHANGES_AND_REVIEW.md`.

| # | Recommendation | What was built |
|---|---|---|
| E1-R1 | Searchable municipality field above the map | "Go to municipality" box in the top bar, all 78 municipalities, synced with map clicks |
| E1-R4 | "Reset Dashboard" button | `↺ Reset dashboard`, red-outlined, top-right |
| E1-R6 (part) | Clarify raw vs normalized | Radio instead of a checkbox, mode badge on the chart, raw number always in the table |
| E1-R3 | Visible data table below the graph | Always-visible scrollable table with sort, filter, CSV export, and full-page expand |
| E1 "simplify category and indicator selection" | One-step selection | Single searchable box over all 174 metrics, labelled `Category › Indicator` |

V9 extends three of these further: the raw/normalized work continues in E1-R5
and E1-R6 below, and the table gains two more columns (E2-R1).

---

## Part 2 — Exercise 1: the rest

### E1-R2 · Display the selected year and value without requiring hover

**Finding:** every participant relied on tooltips; several moved repeatedly
across the chart before activating the right one; one reported the wrong year.

**Built:** a **"Read exact values for year:"** selector sits above the chart,
populated from the years actually present in the current selection and
defaulting to the latest. Below it, a summary card per indicator lists one row
per municipality, each showing **both** numbers side by side and labelled:

```
Poverty Rate · 2022 · [RAW VALUES]
  Mayagüez                    Raw 38.35  ·  Normalized 22.4
  Ponce                       Raw 67.24  ·  Normalized 81.0
  Bayamón                     Raw 62.44  ·  Normalized 70.3
  Across the selected municipalities   Average 56.01 · Median 62.44 · Min 38.35 · Max 67.24
```

No hovering required for any value in the exercises. When projection is on,
the selector also offers the four projected years, each labelled
`(predicted)`, and the card is stamped `PREDICTED`.

The Average/Median/Min/Max row is an Exercise 3 item (E3-R6) delivered early,
because the year card was being built anyway and Exercise 3 Question 3 had a
1-in-6 success rate specifically because the average had to be computed by
hand. It states which mode it was computed on.

### E1-R5 · Make active settings highly visible

**Built two things.**

1. A **persistent breadcrumb strip** across the full width, directly under the
   controls, exactly in the shape Exercise 2 asked for (E2-R3):

   `Guayanilla › Economic Employment › Labor Force › RAW VALUES › Historical only`

   The mode chip is colour-coded (blue = raw, purple = normalized, amber =
   projection on) and it renders in empty states too, so the dashboard never
   sits in an unlabelled condition.

2. A **loud alert bar** that appears whenever a sticky setting is on:

   > ⚠ Normalized values are ON — these numbers are 0–100 positions, not
   > real-world units.   Future projection is ON — dashed points after the
   > last observed year are estimates, not data.
   > `[Show raw values]` `[Turn off projection]`

   The buttons fix the condition in one click.

   **A note on the design choice:** Exercise 2 (E2-O3, E2-O4) offered two
   options — ask for confirmation / auto-reset, *or* make the setting highly
   visible. I took the visibility route deliberately. Silently changing a
   user's settings when they switch indicators creates a new class of
   confusion ("why did my normalization turn off?") and would have made the
   dashboard harder to use in the opposite direction. The combination of a
   permanent breadcrumb, a loud bar, a chart title, a chart badge, a table
   banner and a card badge means a participant would have to ignore six
   simultaneous signals to repeat the 71.42857-instead-of-90.38462 error. Easy
   to switch to auto-reset if you disagree — it is one callback.

### E1-R6 · Clearly label raw, normalized and predicted data

**Finding:** "the tooltip did not make the distinction sufficiently
prominent."

**Built:** the tooltip now names the kind of number explicitly and shows both
at once, so there is nothing to infer:

```
Ponce — Poverty Rate
  Raw Value: 67.24
  Normalized Value: 81.0
  ⚠ PREDICTED VALUE (estimate)
```

The chart also carries a title stating the mode
(`Raw values · Poverty Rate · Ponce · includes projection`), and the y-axis is
labelled `Value (original units)` or `Normalized value (0–100)`.

### E1-R7 · Synchronize the map and panel category controls

**Finding:** for two participants the map showed one category while the side
panel showed another, with no way to tell which control drove which view.

**Built:** the recommendation's preferred option ("ideally, use one category
selector for both"), with an escape hatch. The top control is now explicitly
labelled **"Map Category:"** and carries a checkbox,
**"keep the graph on this category"**, on by default. While it is checked,
changing the map category moves the graph's indicator to that category's
Subcategory Index Score and narrows the optional indicator filter to match —
one control, two views. Unchecking it restores independent control for users
who want to compare a category map against a different indicator, which is a
legitimate analysis.

### E1-R8 · Improve comparison of indicators with different scales

**Finding:** Employment Level and Unemployment Level on one raw axis left the
Unemployment line compressed near the bottom; participants spent considerable
time moving between the lines.

**Built:** two remedies plus automatic detection.

- A new **"Chart layout"** control: *One chart* or
  *Separate axes per indicator*. The second renders one stacked panel per
  indicator with independent y-axes, so each line uses its full vertical
  range.
- An **automatic warning** above the chart when one indicator is being
  squashed, with one-click `[Normalize them]` and `[Separate axes]` buttons.

The detection deserves a note, because the obvious implementation does not
work. I first used the ratio between the indicators' typical magnitudes and a
threshold — and on the study's own example it **failed**: Employment Level and
Unemployment Level differ by only about **2×** by median, well under any
sensible ratio threshold, yet the line really is compressed. The ratio is the
wrong measure. What matters is how much of the *shared vertical axis* each
indicator occupies. Employment spans ~3,700–15,500 and Unemployment
~760–4,400, so on a combined 760–15,500 axis Unemployment gets about **34%**
of the height — and anything under ~35% reads as compressed. `axis_fit()` now
measures that share, and the message adapts: a large magnitude gap (income vs
a percentage rate is ~222×) is reported as "differ in magnitude by roughly
222×", while a modest one is reported as "uses only about 34% of the vertical
axis". Verified both ways, including that two indicators which genuinely share
an axis do **not** trigger a false warning.

### E1-O1 · Replace "N/A" with something meaningful

`N/A` in the Indicator field now reads **"Overall score — no indicator
selection needed"** everywhere it appears, which is the actual meaning.
Exercise 1 and Exercise 3 both flagged this as reading like missing data.

### E1-O2 · Removable selection chips

A chip row at the top of the panel lists everything currently active, each
with its own `×`:

```
Municipality:  Guayanilla ×
Indicators:    Employment Level ×   Unemployment Level ×
```

Removing the last municipality chip closes the panel. When nothing is
selected the row says so rather than sitting empty.

### E1-O3 · Prevent accidental empty selections

"No Data Found" is gone. Each empty state now says what to do:

- no municipality → *"Pick a municipality — type a name in 'Go to
  municipality' at the top, or click one on the map."*
- no indicator → *"Pick at least one indicator in 'Indicator(s) to plot'. The
  search box covers every category at once."*
- real data gap → *"Nothing is stored for this combination of municipality and
  indicator. Try a different indicator, or check the Data Dictionary for which
  years are covered."*

### E1-O4 · Increase graph-point hit areas

Markers enlarged to 9px, hover distance widened to 30px, and — the bigger win
— hover mode switched to **unified**: one hover anywhere at a given year shows
*every* series at that year in one box. Exercise 3's "hover over three
coloured lines, locate the 2022 point on each, remember the values" step
collapses into a single hover (and the year card removes the need for even
that).

### E1-O5 · Highlight the selected municipality and show its name on the map

Selected municipalities now get a white marker and a permanent text label on
the map. The map keeps the viewer's zoom and pan across redraws
(`uirevision`), so selecting something no longer throws away the view they had
scrolled to.

### E1-O7 / E2-R6 · Improve the Data Dictionary

Covered under E2-R6 below, since Exercise 2 specified it in more detail.

### E1-O8 · Explain the dashboard hierarchy

A **"🧭 How this dashboard is organized"** button in the header opens a short
explainer laying out the three levels — Overall MHVI Score → Categories →
Indicators — what scale each uses, which categories currently have data, and
how the two display modes cut across all three. It also explains why the
Overall score has no indicator of its own, which is the root of the "N/A"
confusion in both Exercise 1 and Exercise 3.

### E1-I9 · Stop interactive graph controls firing by accident

**Finding:** participants unintentionally opened the Plotly toolbar, zoomed,
panned, and opened the browser right-click menu, "interrupting the workflow
and sometimes making the graph more difficult to interpret."

**Built:** the trend chart's toolbar is hidden, drag is disabled, scroll-zoom
and double-click are off. Nothing on the chart responds to a stray drag any
more. Export moved to its own labelled button (E2-R4), which is where it
should have been. The *map* keeps its zoom, since panning a map is intentional
there.

---

## Part 3 — Exercise 2

### E2-R1 · Table with year, raw value, normalized value, forecast status

The table now always shows **all four**, regardless of mode:

| Municipality | Indicator | Year | Raw value | Normalized (0–100) | Status |
|---|---|---|---|---|---|
| Juana Díaz | Labor Force | 2022 | 12,670 | 48.3 | Observed |
| Juana Díaz | Labor Force | 2025 | 13,104 | 52.9 | Predicted |

In V8 the normalized column only appeared in normalized mode and the status
column only when projecting. Both are now permanent, so the table answers
"was this raw or normalized?" and "is this real or projected?" without the
user having to recall what they had selected. The banner above states which
column the chart is plotting.

### E2-R2 · Prominent Reset button, including custom report selections

Reset was already there from V8; it now clears **more**. One click restores:
map category, map/graph link, indicator filter, indicators, display mode,
projection, chart layout, municipality-selection mode, municipality, search
box, year, table expansion state, dictionary search and filter, **every
element in the Custom Report Builder**, and closes all three modals. Verified
output by output.

### E2-R3 · Active-setting summary

Delivered as the breadcrumb strip described under E1-R5, in the requested
`Juana Diaz > Economic Employment > Labor Force > Raw Values > Historical
values` form.

### E2-R4 · One clearly labeled export button beside the graph

Directly beneath the chart:

- **`⬇ Export graph (PNG)`** — renders the live figure to a 1400×800 PNG
  client-side, so the file is pixel-for-pixel what is on screen.
- **`⬇ Export data (CSV)`** — see E2-R5.
- **`➕ Add to Custom Report`** — the PDF route.

### E2-R5 · Export preserves the exact current graph

Three separate fixes, because this failed three ways.

1. **The filename records the state.** Exports are named like
   `MHVI_Juana-Diaz_Labor-Force_RAW_2015-2023.csv` /
   `..._NORMALIZED_2015-2028_withProjection.png`, so a file cannot be
   misidentified later.
2. **The CSV carries a settings header.** Before the data rows:
   ```
   # Puerto Rico MHVI dashboard export
   # Exported,2026-10-16 14:22
   # Municipalities,Juana Díaz
   # Indicators,Economic Employment > Labor Force
   # Chart was displaying,Raw values
   # Future projection,OFF
   # Normalization method,min-max to 0-100 per indicator, shared across the selected municipalities and years
   ```
   Then every row with municipality, category, indicator, year, raw value,
   normalized value and Observed/Predicted status.
3. **The Custom Report Builder no longer loses the graph.** This was a real
   bug, and worth spelling out: `handle_report_buttons` created the new
   element with the right indicator, but setting the element's *category*
   dropdown immediately fired `update_report_indicator`, which overwrote the
   indicator with `indicators[0]` of that table. That is exactly the reported
   symptom — videos 7 and 15 started from a Juana Díaz **Labor Force** graph
   and the builder showed **Employment Level**, which is the first indicator
   in `Economic_Employment`. `update_report_indicator` now keeps the incoming
   indicator when it is valid for the category. Separately, "Add to Custom
   Report" creates **one element per selected indicator** instead of silently
   dropping all but the first, and carries the municipalities, display mode
   and projection state into each. The toast confirms what transferred:
   *"Added 2 elements to Custom Reports, using raw values. Open it from the ☰
   menu."*

### E2-R6 · Data Dictionary

Every sub-item from the document:

| Asked for | Built |
|---|---|
| Search field over names **and** definitions | Large search box at the top; matches across friendly name, database name, description, category, units and source; multi-word terms must all match |
| Search without selecting the category first | Search and category filter are independent; search alone works |
| Wrap descriptions | `whiteSpace: normal` on all cells, rows auto-height |
| Freeze the Indicator Name column | `fixed_columns` on the first column, so the name stays visible while reading across |
| Definition in an expandable card, not a wide row | Selecting a row opens a bordered card below with the full description, category, units, source and database name |
| Copy-definition button | `⧉ Copy definition`, appears once a row is selected, confirms "Definition copied to the clipboard" |
| "View definition" link beside each indicator in the main dashboard | Every selected indicator gets an inline definition card in the panel showing category, units, description and source, plus a **"View in Data Dictionary →"** link that opens the glossary with the search pre-filled |
| Explain the hierarchy | The explainer modal under E1-O8 |

Result counts are now stated (*"6 of 166 entries match 'occupied housing'"*),
and a search with no hits says the glossary does not yet cover every indicator
rather than appearing broken. That last point matters: **only 30 of the 167
indicators in the database have a glossary entry at all** — see Part 4.

### E2-R7 · Graph: consistent numeric formatting; a toggle, not a checkbox

- The checkbox became a radio in V8; it is now styled as a **segmented
  toggle** (two adjoining buttons) so the active state is unmissable.
- **One formatting rule**, `fmt_num()`, is used by tooltips, summary cards,
  the table and the CSV. `71.42857` renders as `71.43` everywhere, `52311.4`
  as `52,311`, small values keep 4 decimals, and missing values render as `—`
  rather than `nan`. Table rounding matches displayed rounding, so sorting and
  reading agree.

### E2-O1 · Single selection by default, with a separate compare mode

**"Municipality selection"** is now a toggle: **One municipality** (default)
or **Compare municipalities**. In single mode, a map click or a search
*replaces* the selection, which is what stops the reported problem of "one
municipality remains selected when the other municipality was added". In
compare mode both *add*. Switching back to single keeps the first
municipality and drops the rest.

### E2-O2 · Clear incompatible indicators when the category changes

Handled by the map/graph category link (E1-R7): with the link on, changing
category replaces the indicator selection with one valid for the new category
instead of leaving a stale one behind.

### E2-O3 / E2-O4 · Confirmation or visibility for sticky settings

Delivered as the alert bar with one-click remedies, discussed under E1-R5
including why I chose visibility over auto-reset.

### E2-O5 · Year selector with a summary card

Delivered under E1-R2.

### E2-O6 · Increase the clickable area around graph points

Delivered under E1-O4.

---

## Part 4 — Verification

`app.py` was imported and exercised against the real `pr_dashboard.db` with
Dash and Plotly stubbed (the review environment has no package network).
**169 checks, 0 failures.** Coverage:

- **Callback graph:** every static id resolves to a layout component; no
  output claimed twice without `allow_duplicate`; every `allow_duplicate`
  callback sets `prevent_initial_call`; no callback uses a component as both
  Input and Output (Dash refuses to boot on that); every function signature
  matches its dependency count. 41 callbacks registered.
- **Map:** all 7 categories return data and a year note; the highlight trace
  and permanent label are added; `uirevision` preserves zoom.
- **Selection:** search / map click / chip × / close / reset in both single
  and compare mode, including that single mode replaces and compare adds, that
  removing the last chip closes the panel, and that the reset → cleared search
  box → selection chain terminates instead of looping.
- **Map/graph link:** follows when linked, leaves the graph alone when not.
- **Reset:** all 20 outputs checked individually.
- **Year selector:** built from real data, defaults to latest, adds 4 labelled
  projected years, keeps a still-valid choice.
- **Main callback:** all 8 combinations of raw|normalized × projection on|off ×
  one chart|separate axes. Table always carries all six columns, 75 rows
  without projection and 111 with; every row matches the declared columns;
  observed rows always carry a raw value even in normalized mode.
- **Tooltips and chart:** explicit "Raw Value"/"Normalized Value" labels,
  marker size, unified hover, drag disabled, title states the mode.
- **Scale detection:** catches the study's Employment/Unemployment case (34%
  of axis), catches income-vs-rate (222×), and does *not* fire on indicators
  that genuinely share an axis.
- **CSV:** filename, settings header, all columns, Predicted rows, 112 rows.
- **Dictionary:** name search, description-only search, category filter,
  no-match messaging, detail card, copy button visibility, "View definition"
  pre-fill and modal open.
- **Report builder:** one element per indicator, toast content, the
  indicator-preservation fix, blank element, invalid-indicator fallback, both
  element types.
- **Empty states, quick-fix buttons, table expand/collapse, all three modals,
  formatting helpers, shared-scale normalization, projection on both raw and
  normalized.**

**Not covered offline:** real browser rendering, live Plotly map tiles, actual
PNG download and clipboard behaviour, and the chat/LLM path. Run it locally
once before pushing to the Space.

One thing the harness caught that reading would not have: my first scale-gap
implementation passed its own test but **failed on the study's actual example**
(see E1-R8). Worth keeping the harness around for that reason.

---

## Part 5 — Exercise 3, not implemented

Exercise 3 is almost entirely about the chatbot, and it is a different and
larger piece of work than a UI pass. Its findings were severe — question
success rates of 0/6, 0/6, 1/6 and 2/6 — but the fixes need architecture, not
layout:

1. **Connect the chatbot to the dashboard data and state.** It currently
   cannot see the selected municipality, year, category, indicator or
   normalization status, so it asks users to hover over graphs and read values
   back to it. This needs the dashboard state passed into the chat context on
   every message, plus tool-style data lookups rather than free generation.
2. **Stop it answering from stale context.** It returned 61.69 for Aibonito
   where the graph showed 14.74, and 47.64 for an average that should have
   been 56.013, then later said it did not have the values. Needs a
   "New conversation" button, a visible context warning, and grounding every
   numeric answer in a retrieved row.
3. **Show the data behind every answer**, with "View these values in the
   graph" / "Open indicator definition" links.
4. **"How this score was calculated"** — an expandable list of the indicators,
   definitions, source years, values and method behind a selected MHVI score.
   This one is blocked on the index being finalised, which Exercise 2 also
   notes.
5. **Separate chat export from report export** throughout.

Two small Exercise 3 items are already in V9, since they were one-line
changes in code I was touching anyway:

- The chat's **"Download PDF"** button is now **"📄 Export chat"** with a
  document icon (E3-O1, E3-O2), and it confirms by name:
  *"Conversation exported as MHVI_chat_2026-10-16_14-22.pdf"* (E3-O3) —
  Exercise 3 found that two participants clicked it with no confirmation that
  anything happened.
- The Average/Median/Min/Max row in the year card (E3-R6, partial).

---

## Part 6 — Carried-over follow-ups from the V8 review

Still open, unchanged:

1. **Regenerate `Data_Dictionary` from the real indicator list.** 137 of 167
   indicators have no description, and 136 glossary rows describe indicators
   that do not exist in the database. V9 makes the glossary much easier to
   search and now says plainly when an entry is missing — but it cannot
   invent the 137 missing descriptions, and Exercises 1, 2 and 3 all report
   participants struggling with definitions. **This is the highest-value
   remaining fix and it is a data task, not a code task.**
2. **Update `navigation_guide.py`.** Its step-by-step templates still describe
   the V7 UI ("click the map", "use the Category dropdown"). After V9 those
   instructions are wrong in several places — there is now a search box, a
   reset button, a breadcrumb, a year selector and a single indicator picker.
   Its docstring also references a `layout.py` that does not exist.
3. **Decide what `Overall_MHVI_M_Score` is for.** 910 rows, 2011–2025, wider
   coverage than `Overall_MHVI_Score` (2018–2024), exposed nowhere.
4. **Load or visibly disable the four empty subcategories**
   (`Trauma_Violence_Adversity`, `Food_Water_Basic_Needs`,
   `Neighborhood_Built_Environment`, `Health_Risk_Behaviors`). The dashboard
   presents 6 of 10 domains with no indication that four are missing.
5. **Reconcile duplicate category naming** between the tables
   (`Economic_Employment`) and the glossary
   (`Economic_&_Employment_Conditions`).
6. **Cache the per-metric queries.** `build_series` issues one query per
   (municipality × indicator); three municipalities × three indicators is nine
   round-trips per interaction, and V9 interacts more often (year changes,
   mode changes). `functools.lru_cache` over a read-only SQLite file would
   make this free.
