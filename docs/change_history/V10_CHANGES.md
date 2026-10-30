# MHVI Dashboard — V10 change log

Scope of this pass: **all of Usability study Exercise 3**, plus a pass to cut
the verbosity out of the right-hand panel.

Companion documents: `V8_CHANGES_AND_REVIEW.md` (the first five Exercise 1
items plus the V7 code review) and `V9_CHANGES.md` (the rest of Exercise 1 and
all of Exercise 2).

Change tags in the code name the document and item, e.g. `[E3-R1]` = Exercise
3, Recommended improvement 1; `[E3-O5]` = Exercise 3, "Some other
suggestions" item 5.

---

## Part 0 — Files changed, and what the chatbot owner needs to know

**Changed:** `app.py`, `navigation_guide.py`.
**New:** `dashboard_context.py`.
**Not touched:** `ai_service.py`, `llm_caller.py`, `prompt.py`,
`data_context_builder.py`, `chat_history_manager.py`, `report_*.py`.

The chatbot's own modules are deliberately untouched, since they are
maintained separately. The new behaviour is additive: `app.py` tries to answer
from the dashboard's data first, and anything it cannot answer exactly falls
through to `process_chat_message` exactly as before.

**One optional change in `ai_service.py` would improve this further.** `app.py`
calls:

```python
process_chat_message(question, language, session_id, dashboard_state=state_line)
```

and falls back to the three-argument call on `TypeError`, so nothing breaks
today. Adding the keyword to the signature turns on full state awareness for
the LLM path:

```python
def process_chat_message(user_input, language="en", session_id="default",
                         dashboard_state=""):
    ...
    ai_response = call_llm(chat_context, data_context, language)   # existing
    # dashboard_state is a one-line summary of what the user is looking at;
    # appending it to data_context is enough.
```

`navigation_guide.py` was updated because its step-by-step templates described
controls that no longer exist — see Part 3.

---

## Part 1 — The right-hand panel was too wordy

Fair criticism. V9 answered "users were confused about raw vs normalized" by
adding explanatory prose, and the result was a panel where the help text
competed with the controls.

The principle in V10: **labels and badges stay, paragraphs go.** The things
that actually prevent the raw/normalized error are short and structural — the
breadcrumb, the coloured badges, the chart title, the table's columns, the
card headings. The paragraphs were belt-and-braces, and they cost more in
clutter than they bought in clarity.

What changed:

| Before (V9) | After (V10) |
|---|---|
| Three-to-four-line blue box explaining the display mode | One line: **Raw**: each indicator in its own units. Full text on hover and in Help |
| A full definition card per selected indicator, always expanded | One collapsed `ⓘ` row per indicator; click to read the definition, units, source and glossary link |
| `"One box for everything: type any word (e.g. "poverty", "suicidio", "rent") to search across all categories at once. Options read Category › Indicator."` | gone — the placeholder now says it: *"Indicator — type to search any category…"* |
| `"Type to search. Add as many as you want — each becomes a line on the chart."` | gone |
| `"Municipality selection"` label + `One municipality` / `Compare municipalities` | a compact **One / Compare** toggle, no label |
| `Narrow the list to one category (optional)` collapsible + full-width dropdown | a narrow **All ▾** dropdown sitting beside the indicator box, with a tooltip |
| `How should values be shown?` + `Raw values` / `Normalized 0–100` + `Chart layout` + `One chart` / `Separate axes per indicator`, stacked | two small toggles on one row: **Raw / Normalized 0–100** and **1 chart / Split axes** |
| `Read exact values for year:` | `Values for year` |
| `⬇ Export graph (PNG)`, `⬇ Export data (CSV)`, `➕ Add to Custom Report` | `⬇ PNG`, `⬇ CSV`, `➕ Add to report`, with the long text as tooltips |
| `"Showing 75 rows · the chart is plotting Raw value · every row carries both numbers plus its Observed / Predicted status · sort or filter any column, or use Export for a CSV."` | `75 rows · plots Raw value`, the rest on hover |
| `⤢ Expand to full page` / `⤡ Collapse table` | `⤢` / `⤡` with tooltips |
| Three `<hr>` rules | none; spacing does the work |
| Empty states of 2–3 lines | one line each |

Nothing was deleted outright — every removed sentence is either a tooltip or a
line in the new **Help** panel, reachable from a small **?** beside the
municipality title. That panel also absorbed a "Using the right-hand panel"
section covering each control in one line.

Measured, as a regression guard in the test harness: the panel's visible prose
(mode note + table banner + collapsed definition rows) is now **151
characters**, and the harness fails if it exceeds 400.

The panel header is also tighter — the title, **?** and **✖** sit on one row,
where V9 had a floated Close button above an `<h2>`.

---

## Part 2 — Exercise 3

### The two headline bugs were real, and both are now fixed and tested

Exercise 3 read as "the chatbot hallucinates". It mostly does not. Two
specific defects explain most of the failures.

**1. The Aibonito 61.69 vs 14.74 case is a year bug, not a hallucination.**

`data_context_builder._fetch_overall_score` ends in:

```sql
WHERE fips_code = ? ORDER BY year DESC LIMIT 1
```

There is no year filter anywhere in that module. Aibonito's Overall scores:

| year | 2018 | 2019 | 2020 | 2021 | **2022** | 2023 | **2024** |
|---|---|---|---|---|---|---|---|
| score | 57.79 | 30.13 | 10.90 | 13.46 | **14.74** | 39.10 | **61.69** |

61.688 is Aibonito's **2024** value. The participant asked about **2022**, and
the graph correctly showed 14.744. The assistant was handed the newest row and
answered confidently with it. The model never saw the year.

**2. The 47.64 average was invented because no averaging path existed.**

Nothing in `data_context_builder` computes a statistic. Asked for an average,
the LLM received at most three loose scores in a sentence and did the
arithmetic itself. The real figures:

| Municipality | Poverty Status Past 12 Months, 2022 |
|---|---|
| Mayagüez | 38,354 |
| Ponce | 67,242 |
| Bayamón | 62,443 |
| **Average** | **56,013** |

That matches the study's expected 56.013 exactly (the document writes
thousands with a period). The assistant's 47.64 corresponds to nothing in the
database.

### E3-R1 · Connect the assistant to the dashboard's data

New module `dashboard_context.py`. Value questions are answered by
**retrieval**, never generation:

- it reads the dashboard's live selection, so the user never restates it;
- **a year named in the question wins** — the fix for bug 1;
- it computes average / median / min / max itself — the fix for bug 2;
- it returns the rows it used, so the answer can show its own evidence;
- it returns `None` when it cannot answer exactly, and the existing LLM path
  handles the message unchanged.

It does not import `app.py`. The caller injects `series_for_assistant`, which
is the same `build_series → add_normalized → add_forecast` pipeline the chart
uses, so the assistant and the chart **cannot** disagree. That is the
structural fix for "chatbot and graph show different numbers".

Verified against the study's own cases: the Aibonito question now returns
14.744 with `year == 2022` while the dashboard sits on 2024, and the average
question returns 56,013 with its three rows attached. A year the data does not
cover is refused by name — *"I don't have 1995 for that indicator. Stored
years are 2018–2024."* — rather than silently answered with a different year,
which is how bug 1 stayed invisible.

### E3-R2 · Synchronize the assistant with the dashboard state

A `dashboard-state` store is published by the main callback on every
interaction, carrying municipalities, indicators, year in focus, display mode
and projection flag. `dashboard_context` reads it directly. For questions that
fall through to the LLM, `state_summary()` renders it as one line
(*"Dashboard is currently showing — municipalities: Ponce; indicators: Labor
Force; year in focus: 2022; display mode: raw values; future projection:
off."*) and passes it as the optional kwarg described in Part 0.

### E3-R3 · Show the data behind every answer

A retrieved answer renders as a distinct bubble carrying:

- a green **✓ Read from dashboard data** stamp — so a user can tell at a glance
  whether a number came from the database or from the model, which the study
  found impossible;
- the sentence;
- a small table, one row per municipality, with the year and value, projected
  rows marked `⚠`;
- the normalization method, when normalized values are in play;
- **`View these values in the graph`** — applies those exact municipalities,
  indicator, year and mode to the dashboard and opens the panel;
- **`Open indicator definition`** — opens the glossary with the search
  pre-filled.

Both buttons were asked for by name in the document. LLM answers get no stamp,
which is the honest distinction.

The plain-text form of a grounded answer is written to the chat history, so
the PDF transcript keeps both the answer and its evidence.

### E3-R4 · Reset the conversation, and warn while context is live

- A **🗘 New** button in the chat header issues a fresh session, clears the
  history, drops any pending report and reseeds the welcome message.
- **Reset dashboard also starts a clean conversation**, since "start clean for
  the next exercise" is exactly what that button means. Its tooltip says so.
- While a conversation has history, a slim amber line sits above the input:
  *"⚠ This conversation already has 6 earlier messages — answers may draw on
  them. Use 🗘 New to start clean."* Translated for Spanish.

### E3-R5 · Replace "N/A" and show the calculation components

`N/A` became **"Overall score — no indicator selection needed"** back in V9.
V10 adds the second half: a collapsed **🧮 How the Overall MHVI Score was
calculated** row appears in the panel whenever an index score is selected,
with the method taken from `MHVI Methodology Summary_Updated.docx`:

1. every indicator's raw values are ranked 0–100 across the 78
   municipalities, inverting metrics where a high value means *less*
   vulnerability, so 100 always means most vulnerable;
2. indicator ranks are summed within each subcategory and percentile-ranked
   again to give the Subcategory Index Score;
3. subcategory ranks are summed and percentile-ranked a final time.

It then lists the actual components — the subcategories feeding the Overall
score, or the indicators inside a subcategory — and **discloses the gap**:

> The methodology specifies 9 subcategories. 6 currently hold data, so the
> Overall Score is built from those 6 only. Treat it as provisional until the
> remaining subcategories are loaded.

That disclosure seemed worth making prominent. Participants were asked which
indicators feed the index and none could find out; the honest answer includes
the fact that a third of the intended inputs are missing.

For a subcategory it also notes how many of its indicators have no glossary
definition yet.

### E3-R6 · Multi-municipality calculations

Mostly delivered in V9 (year selector, one row per municipality, average /
median / min / max). V10 completes the document's remaining points:

- **Value type in the name.** Card headings now read exactly as asked —
  **"Raw Poverty Status Past 12 Months, 2022"** — rather than relying on a
  separate badge.
- **Don't let normalized values answer a raw question.** If the question says
  "raw" or "normalized", that wins over the dashboard's mode, and the answer
  says so: *"You asked for raw values, so that is what I used — the dashboard
  is currently showing normalized."* A single-value answer always reports both
  numbers, so neither can be misread.

### E3-O1 / E3-O2 / E3-O3 · Export naming and confirmation

Delivered in V9: the button is **📄 Export chat** with a document icon, and it
confirms by name — *"Conversation exported as MHVI_chat_2026-10-23_14-22.pdf"*.

### E3-O4 · Separate conversation export from report export

Three distinct, differently-labelled paths: **📄 Export chat** in the chat
header (the conversation), **⬇ PNG / ⬇ CSV** under the graph (the current
chart and its data), and **➕ Add to report → 🖨 Export report to PDF** (the
Custom Report Builder). The report modal also explains what arrives in it.

### E3-O5 · "Export this conversation" should trigger the export

It now does. `is_export_chat_request()` catches "export this conversation",
"save the chat as a pdf", "download the transcript" and the Spanish
equivalents, and is checked **before** the report keywords — the study found
the assistant reading these as a request for a municipality report, because
`_is_report_intent` matches a bare "pdf". The export runs and the reply names
the file.

---

## Part 3 — Two things found along the way

### The forecast did not match the documented methodology

`MHVI Methodology Summary_Updated.docx` specifies **Holt linear trend
exponential smoothing**, "designed for data with a steady upward or downward
trend… recent data points are assigned more mathematical weight than older
ones."

The dashboard was using `np.polyfit(x, y, 1)` — ordinary least squares, which
weights a 2015 observation exactly as heavily as a 2024 one. Those are
different methods with different answers. On a series that is flat and then
climbs:

```
series  [10, 10, 10, 10, 10, 20, 30, 40]
Holt -> [50.3, 60.7, 71.0]     follows the recent climb
OLS  -> [35.7, 39.8, 43.8]     still dragged down by the flat years
```

V10 implements Holt with level and trend smoothing, picking α and β by a
coarse grid search on one-step-ahead squared error — no new dependency. Short
series (fewer than four points) still fall back to the straight line, and a
flat series projects flat with no drift. The chart badge, the CSV header and
the calculation panel now all name Holt.

Worth a look from your side: this changes projected numbers, so if any
existing figures were produced with the polyfit version they will no longer
match.

### `navigation_guide.py` was describing a dashboard that no longer exists

Its templates told users to "look at the top of the dashboard and find the
Category dropdown", then "find the map… click on {municipality}" — the exact
hunt-the-map behaviour the study flagged and V8 removed. Since the chat is
what participants were told to use, it was actively sending them down the old
path.

Rewritten for the V10 interface in both languages: the search box, "Map
Category", the single indicator box, the year selector, the table, the export
buttons and Reset. Two incidental fixes: the docstring referenced a
`layout.py` that has never existed in this folder, and `csv` was listed as an
unsupported feature, which stopped being true in V9.

---

## Part 4 — Verification

`app.py` and `dashboard_context.py` were imported and exercised against the
real `pr_dashboard.db`, with Dash, Plotly and the chat modules stubbed.
**267 checks, 0 failures.** The V9 suite still passes unchanged; the V10
additions cover:

- **Panel verbosity** — definition rows collapsed by default, each summary
  under 90 characters with the full text as a tooltip; table banner under 40
  characters; total visible panel prose measured at 151 characters against a
  400-character ceiling.
- **Holt forecast** — tracks a recent level shift more closely than the old
  polyfit line; flat series projects flat; clean straight line extrapolates
  correctly; 2-point and 1-point and empty series handled; still fills four
  years of both raw and normalized.
- **Dashboard state** — published on every interaction, including when nothing
  is selected; renders to a one-line summary.
- **The Aibonito bug** — asked about 2022 with the dashboard on 2024, the
  answer is 14.744 with `year == 2022`; with no year named the dashboard's
  year is used; a year outside the data is refused by name.
- **The average bug** — 56,013 computed from three listed rows, the reported
  average verified equal to the mean of those rows; median and max too.
- **Raw vs normalized in answers** — an explicit request overrides the
  dashboard and says so; a single value reports both numbers.
- **Intent routing** — export vs report vs value vs chat, in both languages,
  including that a report request still reaches the report flow and that
  nothing-selected declines to guess rather than inventing.
- **Question parsing** — years, statistics, explicit mode, municipality names
  with accents and overlaps ("San Juan" vs "Juana Díaz"), indicator matching
  ("total insured population", "labor force").
- **Chat rendering** — the data stamp, the evidence table, both action
  buttons, the Spanish rendering, the transcript text, and the
  apply-to-dashboard button including a malformed payload.
- **Conversation lifecycle** — new session, reset-also-resets-chat, the stale
  context warning appearing and translating.
- **`generate_ai_response` routing** — grounded path stamped, LLM path not
  stamped, export path triggering a download and confirming by filename, both
  sides recorded in history, empty message ignored.
- **Calculation components** — method text, inversion, the 9-vs-6 disclosure,
  Holt named, subcategory component lists, and no block for a plain indicator.

**Not covered offline:** browser rendering, live map tiles, the actual
PNG/clipboard/download behaviour, and the real LLM. In particular the grounded
path has been tested hard, but the **fall-through** to `process_chat_message`
has only been tested against a stub — worth a few live questions before
redeployment, together with the compatibility check against the current
`ai_service.py`.

---

## Part 5 — Still open

1. **Regenerate `Data_Dictionary`.** 137 of 167 indicators have no
   description, and 136 glossary rows describe indicators that are not in the
   database. All three exercises found participants struggling with
   definitions. V10 surfaces the gap honestly in three places now (the `ⓘ`
   rows, the glossary's no-match message, and the calculation panel's count of
   undefined indicators) but it cannot write the missing text. **Highest-value
   remaining item, and it is a data task.**
2. **Fix the year-blind lookups in `data_context_builder.py`.** The grounded
   layer intercepts value questions before they reach it, so the Aibonito
   failure mode is closed in practice — but the module is still year-blind for
   anything that does reach it. The fix is small, in `_fetch_overall_score`
   and `_fetch_category_score`:
   ```python
   def _fetch_overall_score(conn, fips, year=None):
       if year is not None:
           df = pd.read_sql("SELECT value FROM Overall_MHVI_Score "
                            "WHERE fips_code = ? AND year = ?",
                            conn, params=(fips, year))
       else:
           df = pd.read_sql("SELECT value FROM Overall_MHVI_Score "
                            "WHERE fips_code = ? ORDER BY year DESC LIMIT 1",
                            conn, params=(fips,))
   ```
   with the year parsed from the question. I left it alone because that file
   is maintained separately — say the word and I will patch it.
3. **Load or visibly disable the four empty subcategories.** This now matters
   more than it did: the calculation panel states that the Overall Score is
   built from 6 of 9 subcategories, which is a real caveat on every number the
   dashboard shows.
4. **Decide what `Overall_MHVI_M_Score` is for** — 910 rows, 2011–2025, wider
   coverage than `Overall_MHVI_Score` (2018–2024), still exposed nowhere.
5. **Reconcile duplicate category naming** between the tables
   (`Economic_Employment`) and the glossary
   (`Economic_&_Employment_Conditions`).
6. **Cache the per-metric queries.** `build_series` issues one query per
   (municipality × indicator), and V10 calls it more often — the assistant
   runs it on every value question. `functools.lru_cache` over a read-only
   SQLite file would make this free.
7. **In-memory chat history.** `chat_history_manager` holds history in a
   module-level DataFrame, so it is lost on restart and not shared between
   workers. Fine for a single-worker Space; worth knowing before scaling.
