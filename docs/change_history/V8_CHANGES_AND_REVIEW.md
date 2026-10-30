# MHVI Dashboard — V8 review and change log

Reviewed: `V7_HuggingFace/` (app.py 63 KB, data.py, pr_dashboard.db).
Written: 2026-09-14.

---

## Part 1 — What I found wrong in V7

### Crash / correctness bugs

**1. `datetime` is used but never imported.** `app.py` line 1486 calls
`datetime.now()` inside `export_chat_pdf`, but the module has no
`from datetime import datetime`. Every click of the chat's **Download PDF**
button raised `NameError` and returned nothing. Fixed.

**2. `Overall_MHVI_M_Score` leaked into the Category dropdown.** The startup
query excludes `Overall_MHVI_Score` but not `Overall_MHVI_M_Score`, so the
MHVI-M table was treated as a selectable subcategory. Selecting it queried
`WHERE indicator_name = 'Subcategory Index Score'` against a table whose only
indicator is `Overall MHVI-M Score`, producing a silently blank map. Fixed by
filtering against an explicit non-subcategory list. (The MHVI-M table has
910 rows spanning 2011–2025 and is currently unused anywhere in the app —
worth deciding whether it should be a first-class map layer.)

**3. The map mixed years across municipalities.** The choropleth used a
*correlated* subquery — `MAX(year) ... WHERE t2.fips_code = t.fips_code` — so
each municipality was painted with *its own* latest year. Any municipality
with a shorter series was being compared against other municipalities from a
different year, with nothing on screen to say so. Fixed: one `MAX(year)` for
the whole layer, and the year is now printed under the control bar.

**4. Normalization destroyed the comparison it was meant to enable.** Each
municipality's series was min–max scaled *independently*, which forces every
line to span exactly 0–100. Two municipalities with wildly different poverty
rates rendered as the same line. Fixed: normalization now uses one shared
scale per indicator across all selected municipalities and years, so relative
position is preserved.

**5. The forecast horizon was hardcoded to 2025–2028.** Several tables already
reach 2025, so "predict future years" was partly predicting the past. Now the
horizon is the four years after each series' own last observation.

**6. `time.sleep(3)` inside a callback.** `clear_toast` blocked a worker thread
for three seconds on every "Add to Custom Report" click. On a Hugging Face
Space with a small worker pool this is a self-inflicted stall, and it raced
with the other callback writing the same output. Removed.

**7. SQL was built by f-string interpolation of user-selected values** —
e.g. `WHERE fips_code = '{clicked_fips}' AND indicator_name = '{ind}'`. Values
come from your own dropdowns, so this is not an active injection hole, but it
breaks outright on any indicator name containing an apostrophe and it is the
kind of thing that stops being safe the moment an input becomes free-text. All
queries in the new file are parameterised; table names are validated against
an allow-list before interpolation.

### Structural / maintenance problems

**8. `data.py` is dead code that `app.py` reimplements.** `data.py` has a clean,
parameterised, allow-listed data layer — and `app.py` ignored it and wrote its
own `get_db_connection`, `query_axis_data`, `fetch_map_data` and metadata
loader inline. Worse, `data.py` *was* still being imported transitively (via
`ai_service`), so the app downloaded the plotly county GeoJSON **twice** at
startup and maintained two divergent copies of the same query logic (they had
already drifted — see bug 3). V8 imports the shared layer and deletes the
duplicates.

**9. Bare `except:` clauses everywhere** (~15 of them), several wrapping the
whole query-and-connection block. Any error — a typo in a table name, a
corrupted DB, a `KeyboardInterrupt` — surfaced to the user as an empty chart
with no message. Narrowed to `except Exception` with explicit empty-state
messaging in the paths I rewrote.

**10. `navigation_guide.py` describes a file that does not exist.** Its
docstring and comments reference `layout.py` ("Templates only reference UI that
actually exists in layout.py"). There is no `layout.py` in this folder — the
layout lives in `app.py`. Leftover from an earlier refactor; the templates
themselves are still accurate, but note that **the chatbot's navigation
instructions now describe the V7 UI**, not V8. They will need updating (see
"Follow-ups" below).

### Data-integrity problems (not code bugs, but they surface as UI bugs)

**11. The Data Dictionary is 82% disconnected from the database.**

| | count |
|---|---|
| distinct indicators stored in the DB | 167 |
| rows in `Data_Dictionary` | 166 |
| DB indicators that **have** a dictionary entry | **30** |
| DB indicators with **no** entry | 137 |
| Dictionary rows describing indicators **not in the DB** | 136 |

This is why the per-indicator descriptions in the old accordion almost always
read "No description available." The two lists appear to have been built from
different sources (the dictionary looks like it was written against the
*planned* indicator set). Nothing in the code can fix this — the dictionary
needs to be regenerated from `raw_name` values that actually exist.

**12. The Data Dictionary category filter returned nothing for most
categories.** The filter's options were built from *table names*
(`Economic_Employment`) but the dictionary's `category` column uses different
strings (`Economic_&_Employment_Conditions`). Only 108 of 166 rows used a
category that the filter could even produce. Fixed by driving the filter off
the dictionary's own distinct categories — though the underlying duplication
(`Economic_Employment` *and* `Economic_&_Employment_Conditions` both present)
should be cleaned up in the data.

**13. Four subcategory tables are empty:** `Trauma_Violence_Adversity`,
`Food_Water_Basic_Needs`, `Neighborhood_Built_Environment`,
`Health_Risk_Behaviors`. They are silently dropped from the UI, which is the
right behaviour, but it means the dashboard currently presents 6 of 10
subcategories with no indication that four domains are missing. Consider
showing them greyed out with "data not yet loaded".

**14. `Healthcare_Access` holds 106 of the 167 indicators**, many of them
80-character Spanish ICD-range labels. This is the single biggest driver of
the "indicator selection is tedious" finding — see change 5 below.

### Smaller things

- `app.py` still carried `# %%` Jupyter cell markers and a "V6" heading.
- `import os`, `import sqlite3`, `import json`/`urlopen` were partly unused.
- No `server = app.server`, so the Space could only run via `python app.py`,
  never gunicorn.
- `certifi` is imported by `data.py` but was absent from `requirements.txt`
  (it happened to arrive as a transitive dependency of `openai`).
- The map had no colour-bar title and no fixed colour range, so the legend
  rescaled between categories and looked like the data had changed.
- `db_metadata` was serialised to JSON and re-parsed (`json.loads`) on every
  single callback invocation, for no reason.

---

## Part 2 — The five requested changes

### 1. Searchable municipality selection

The dropdowns in V7 were already `searchable`, but the only way to *reach*
them was to click the map first — the whole right panel was hidden until a
map click fired. That is the real finding.

Added a **"Go to municipality"** search box in the top control bar, always
visible, listing all 78 municipalities. Selecting one opens the detail panel
and focuses that municipality, exactly as clicking the map does. A map click
now also writes back into the search box, so the two stay in sync and the box
always shows where you are.

Mental model: **search box or map click = "go here"; the panel's
"Municipalities to compare" box = "add more to the chart."**

### 2. Reset button

**↺ Reset dashboard**, top-right of the control bar, outlined in red so it
reads as a distinct action rather than another filter. One click restores:
map category → Overall MHVI Score, municipality search → empty, selected
municipalities → none, detail panel → closed, category filter → All,
indicators → Overall MHVI Score, display mode → Raw, forecast → off, table →
collapsed to in-panel, left nav → closed, dictionary filter → All.

### 3. Raw vs. normalized

This was ambiguous in three separate ways, and all three are addressed:

- **It was a checkbox in a list of unrelated toggles.** A checkbox reads as
  "add a thing", not "switch between two mutually exclusive views", and it sat
  next to the ML forecast toggle. It is now a labelled **radio group** —
  "Raw values" vs "Normalized 0–100" — in its own bordered block.
- **Nothing on the chart said which you were looking at.** There is now a
  coloured badge directly above the chart (blue `RAW VALUES` / purple
  `NORMALIZED 0–100`), a matching y-axis title, and a line above the table
  naming which column the chart is plotting.
- **The table now always shows the raw number**, and adds a starred
  `★ Normalized (0–100)` column when that mode is on. You can always see both,
  so there is no state in which "which number is this?" is unanswerable.

A live explainer box under the radio spells out what the current mode does,
including the point that trips people up: **the MHVI index scores are already
0–100 percentile ranks**, so "normalizing" them again is rescaling a scale.
The explainer says so when an index score is selected.

### 4. Tabular data window

The old `<html.Details>` accordion — one collapsed section per indicator, each
hiding a small year/value table — is gone. The table is now:

- **visible by default**, in a fixed 300px-tall scrollable pane;
- **the data behind the chart**: Municipality / Indicator / Year / Raw value
  (+ Normalized, + Type when forecasting), so it always matches what is plotted;
- **sortable and filterable** on every column (native DataTable controls);
- **exportable to CSV** via the built-in Export button;
- **expandable to full page** via `⤢ Expand to full page`, which switches the
  section to a fixed full-viewport overlay; the button becomes
  `⤡ Collapse table`.

On the pop-up question: I went with the full-page overlay rather than a real
browser popup. A `window.open` popup would need a second Dash page served from
the same app and would be blocked by most popup blockers, and the Space runs
in an iframe on hf.co, which makes that worse. The overlay is pure CSS,
behaves identically in the Space and standalone, and keeps all the table's
state (sort, filter, scroll position) intact when you collapse it.

### 5. Category and indicator selection

Replaced the two chained dropdowns with **one searchable box spanning all 174
metrics**. Options are labelled `Category › Indicator`, so typing `poverty`,
`suicidio`, `rent` or `F20-29` finds the indicator directly without knowing or
choosing its category first. Selecting is one step instead of two, and you can
select indicators from *different* categories in the same chart — which V7
could not do at all.

Two supporting touches:

- Indicator names are humanised: `_`/`-` become spaces, and the `_Cases` /
  `_Rate` suffixes — which exist on most indicators in this dataset and are
  the most common source of "wrong number" mistakes — render as explicit
  `[count]` / `[rate]` tags.
- The old category dropdown survives as an **optional** collapsed "Narrow the
  list to one category" control for people who prefer to browse. It never
  blocks selection, and anything you have already selected stays visible in
  the list even when filtered out.

When you plot several raw indicators with different units on one axis, the
chart now shows an inline warning suggesting the normalized view.

---

## Part 3 — Verification

`app.py` was imported and exercised against the real `pr_dashboard.db` with
Dash and Plotly stubbed (no network in the review environment). Checks run:

- every callback id resolves to a component in the layout;
- no output is claimed by two callbacks without `allow_duplicate`;
- every `allow_duplicate` callback sets `prevent_initial_call`;
- no callback uses a component as both Input and Output (Dash refuses to boot
  on that — it caught one in my first draft);
- the map callback returns data for all 7 categories;
- search / map-click / close / reset each produce the right selection state,
  and the reset→search-box→selection chain terminates instead of looping;
- chart+table across all 4 combinations of raw|normalized × forecast on|off:
  correct columns, every declared column present in the row dicts, forecast
  starting the year after the last observation;
- normalization verified to use a shared scale (municipality spans are no
  longer all exactly 100);
- empty states: no municipality, no indicator, no data — all return cleanly;
- dictionary filter, report builder (graph and table), table expand/collapse.

All passing. **Not covered offline:** actual browser rendering, real Plotly
map tiles, and the chat/LLM path. Run it locally once before pushing to the
Space.

---

## Part 4 — Follow-ups worth doing next

1. **Regenerate `Data_Dictionary` from the real indicator list.** 137 of 167
   indicators have no description. This is the highest-value data fix and it
   feeds the tooltips, the glossary, and the chatbot.
2. **Update `navigation_guide.py`.** Its step-by-step templates describe the
   V7 UI ("click the map"). They should mention the search box and the reset
   button, or usability testers will get instructions that no longer match.
3. **Decide what `Overall_MHVI_M_Score` is for.** It has more year coverage
   (2011–2025) than `Overall_MHVI_Score` (2018–2024) and is not exposed
   anywhere.
4. **Load or hide the four empty subcategories.**
5. **Reconcile the duplicate category naming** between the tables and the
   dictionary.
6. **Cache the per-metric queries.** `build_series` issues one query per
   (municipality × indicator). Five municipalities × five indicators is 25
   round-trips per interaction. `functools.lru_cache` on a read-only SQLite
   file would make this free.
7. **The chatbot does not know about any of the V8 controls.** Its navigation
   answers and the welcome bubble examples should be refreshed.
