# Changelog

Detailed notes for each version are in `change_history/`. The usability-study
item each change answers is given in brackets: E1 / E2 / E3 = Exercise 1 / 2 / 3.

## V11 — dashboard and AI-CHATBOT branch merged

Details: `change_history/V11_MERGE.md`.

- The V10.1 dashboard now runs inside the AI-CHATBOT branch's structure, with
  its assistant window, accounts, chat history and "Report an issue". The
  dashboard looks and works exactly as in V10.1 (checked component by
  component and callback by callback).
- Value questions in the new assistant are answered from the dashboard's data
  first, with the rows used and "View these values in the graph" [E3].
  "Export this conversation" downloads the chat PDF [E3]. Reset also starts a
  new chat [E3].
- The assistant's other lookups and municipality reports read the same table
  (Overall MHVI Score) and the same year as the map. Before, they read a
  different table and the newest, incomplete year — e.g. Aibonito 46.79
  where the map showed 14.74.
- Sign-in is optional, switched by `REQUIRE_LOGIN` (0 now; 1 to require it).
- The site keeps working when MongoDB is unreachable; chat history, sign-in
  and tickets say "temporarily unavailable". A database outage no longer
  stops the app from starting.
- "MHVI-M" renamed to "MHVI" throughout; the app now starts with
  `python MHVI_Dashboard_App.py`.
- Ready for Hugging Face: port 7860, debug off, Python 3.12 image, partner's
  version requirements kept.

## V10.1 — publishing cleanup

- Map shows one shared year across all categories — the latest year in which
  **every** category has all 78 municipalities (currently 2023) — so none
  appear gray. Previously Florida was gray on the Overall map (no 2024 value),
  and Education 2024 / Healthcare 2025 left 67 and 26 gray.
- The data-year note under the controls was removed.
- The panel opens on the same year the map is showing, so a clicked
  municipality's number matches its colour.
- Logos load relative to `app.py`, not the launch folder, and live in `assets/`.
- Release folder created: backups and working files left behind in
  `V7_HuggingFace`; `.env.example`, `.gitignore`, `.dockerignore`, README added.
- Docker base image Python 3.9 → 3.10, matching local development.
- Smoke test moved to `tools/`, now genuinely runs without an API key, and
  checks for gray municipalities.

## V10 — assistant connected to the data; quieter side panel

- Assistant answers value questions from the database, using the dashboard's
  current selection [E3]. Fixed: a year in the question was ignored (Aibonito
  2022 answered with 2024's 61.69 instead of 14.74), and averages were made up
  by the model (47.64 instead of 56,013).
- Answers show the rows they came from, with "View in graph" and "Open
  definition" buttons [E3]. New-conversation button, stale-context warning,
  Reset also resets the chat, "export this conversation" works [E3].
- "How this score was calculated" panel for index scores [E3].
- Projections use Holt linear-trend smoothing, as the methodology specifies
  (was a straight-line fit).
- Side panel shortened: one-line notes, collapsed definitions, help moved
  behind a "?" button.
- Chat navigation instructions rewritten for the current interface.

## V9 — rest of Exercise 1, all of Exercise 2

- Year selector with summary cards: exact values without hovering, plus
  average / median / min / max [E1, E2].
- Breadcrumb of active settings across the top; loud alert while normalized
  or projected values are on [E1, E2].
- Tooltips and titles say "Raw", "Normalized" or "Predicted" [E1].
- Map category drives the graph by default [E1]; split-axes layout and a
  warning when one line is squashed flat [E1].
- Selected municipality labelled on the map; removable chips; clearer empty
  states; larger hover targets; graph toolbar disabled to stop accidental zoom
  [E1].
- Table always shows raw, normalized and observed/predicted status [E2].
- PNG and CSV export of the current graph; report builder keeps the current
  graph (it used to switch the indicator) [E2].
- Data dictionary: full-text search, frozen name column, expandable
  definition with copy button, links from the panel [E2].
- One municipality at a time by default, with a Compare mode [E2].

## V8 — first usability fixes, code review

- Searchable "Go to municipality" box [E1]; Reset button [E1].
- Raw vs normalized as an explicit choice [E1].
- Data table visible by default, expandable to full page [E1].
- One searchable box for all indicators instead of category → indicator [E1].
- Fixed: chat PDF export crashed (missing import); MHVI-M table appeared as a
  blank category; map mixed years across municipalities; normalization broke
  comparisons between municipalities; SQL built by string formatting.
