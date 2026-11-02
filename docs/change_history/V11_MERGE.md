# V11 — Merging the V10.1 dashboard with the AI-CHATBOT branch

Branch: `integration/v10-dashboard-chatbot`, started from `origin/AI-CHATBOT`
(`1ee30be`). Nothing was changed on `main` or `AI-CHATBOT`.

## Goal

- The dashboard looks and works exactly as V10.1 (the version from the three
  usability exercises).
- The AI-CHATBOT branch's assistant, accounts, chat history and tickets are
  connected to it and read the same, correct data.
- Sign-in optional for now, easy to make mandatory again.
- Everything runs on Hugging Face Spaces; the dashboard keeps working when
  MongoDB cannot be reached.
- The partner branch's minimum package versions are kept as they were.

## Structure

The two versions were organised differently (one `app.py` vs.
`layout.py` + `callbacks.py` + packages), and both had a chat window using
the same component ids, so this was a structured merge rather than a
`git merge`.

| Where | What |
|---|---|
| `dashboard/` (new) | V10.1's `app.py`, split into `core.py` (data, helpers), `layout.py` (the page), `callbacks.py` (behaviour), `context.py` (V10's `dashboard_context.py`), `chat_bridge.py` (grounded answers in the new chat window). |
| `assets/dashboard.css` (new) | V10.1's styles, moved out of `app.py`'s page template. |
| `assets/logos/` | the three logos (the partner entry point already pointed here). |
| `data.py` | V10.1's version (reads `Overall_MHVI_Score`) plus the shared map-year rule. |
| `pr_dashboard.db` | V10.1's database (the branch had an older copy with about a fifth of the rows and no Data Dictionary). |

The V10.1 callbacks keep their `@app.callback` decorators unchanged: in
`dashboard/callbacks.py`, `app` is a small recorder, and
`register_dashboard_callbacks(real_app)` hands them to the real app at start.

## Removed

- **V10.1's own chat window and its callbacks** (toggle, language picker,
  send/answer, 🗘 New, stale-context warning, chat PDF, report download,
  header translation). The partner's window replaces them; its ⋮ menu has New
  Chat, Chat History and Download Chat PDF.
- **The V6 dashboard callbacks and layout pieces inside the partner's
  `callbacks.py` / `layout.py`** (map, side panel, help and report modals).
  They were the older dashboard the partner branch started from, not partner
  work; V10.1 replaces them.
- **Index Breakdown** (V6's included/missing indicator boxes) was not carried
  over, to keep the dashboard identical to V10.1. V10.1's 🧮 row covers how a
  score is built.
- The stray `mongodb-community` file (saved terminal output).

## Changes to the partner's code, and why

| File | Change | Why |
|---|---|---|
| `MHVI_Dashboard_App.py` | Builds the page from `dashboard/`, registers the dashboard callbacks and the grounded-answer hook; runs on `0.0.0.0`, port `$PORT` (7860), debug only with `DASH_DEBUG=1`; exposes `server`. | Plug in V10.1; Hugging Face needs 0.0.0.0:7860; debug must be off on a public site. |
| `layout.py` | `build_layout(dashboard_children)` puts the V10.1 dashboard inside the login gate. Account button moved from a fixed corner into the dashboard header (it would have covered the logos). Login page: shown or hidden by `REQUIRE_LOGIN`, plus a "← Back to the dashboard" link when sign-in is optional. V6 builders removed. | Plug in V10.1; optional sign-in. |
| `callbacks.py` | Gate honours `REQUIRE_LOGIN`; new `request_login` and `account_button_label` ("👤 Sign in" / "⚙ Settings"); settings panel opens only when signed in. `generate_ai_response` reads `dashboard-state`, passes it on, and renders grounded answers and "export this conversation". Reset also starts a new chat. Chat history panel says "Sign in to save…" for anonymous visitors. MongoDB checks (below). V6 dashboard callbacks removed. | Optional sign-in; Exercise 3 fixes in the new window; database resilience. |
| `chat/ai_service.py` | `register_dashboard_answerer()` hook; `process_chat_message(..., dashboard_state=None)` asks it first. Grounded answers and export requests need no database or AI key; their history is saved when MongoDB is up. Other questions return "temporarily unavailable" when it is down. Report message names the data year. | Answers the study's value questions from the chart's own numbers; works during outages. |
| `chat/data_context_builder.py`, `chat/report_data_builder.py` | Read `Overall_MHVI_Score` / "Overall MHVI Score", and use the map's year instead of `ORDER BY year DESC LIMIT 1`. | In this database `Overall_MHVI_M_Score` is a different 910-row table: the assistant said Aibonito 2022 = 46.79 where the map shows 14.74. The newest year is incomplete for several tables. |
| `chat/prompt.py`, `chat/site_knowledge.py`, `chat/navigation_guide.py` | Describe the V10.1 interface ("Map Category", "Go to municipality", the indicator search box, "Values for year", Reset, PNG/CSV, "➕ Add to report", Data Dictionary). Removed Index Breakdown / Plot button / "Category dropdown". CSV and sign-in no longer listed as missing; a sign-in how-to was added. Site knowledge states whether sign-in is required. | The assistant must never describe buttons that are not there. |
| `chat/__init__.py` | exports `register_dashboard_answerer`. | |
| `mongodb/client.py` | 3-second server timeout (`MONGODB_TIMEOUT_MS`), `is_available()` (cached ping), `mark_unavailable()`, index creation skipped while down and done when it returns, a bad `MONGODB_URI` no longer crashes the import, password masked in log lines. | Item 15: keep running without the database. PyMongo's default 30 s wait froze every page. |
| `tickets/routes.py` | Admin provisioning at start-up is skipped (with a log line) when MongoDB is unreachable. | **Deviation:** a database outage otherwise stopped the whole site from starting. |
| `auth/policy.py` (new) | `login_required()` reads `REQUIRE_LOGIN` (default `1`). | One switch for optional / mandatory sign-in. |

Naming: the project dropped the "for Minors" framing, so "MHVI-M" became
"MHVI" on the login page, the admin page, in the report prompt and in
docstrings. The entry file was renamed to `MHVI_Dashboard_App.py`, and
the stale notebook copy `MHVIM_Dashboard_App.ipynb` was removed.

When MongoDB is down: the dashboard is shown even with `REQUIRE_LOGIN=1`
(a sign-in form that cannot work is not shown); the Sign in tooltip, sign-in
form, chat history, assistant (non-value questions), `/delete` and `/name`,
Download Chat PDF and "Report an issue" all say "temporarily unavailable".
Any other database error inside a callback leaves the page unchanged.

## Not changed

- `requirements.txt` — the partner's minimum versions are kept (pandas ≥ 3
  and numpy ≥ 2.4 need **Python 3.11+**; the Docker image uses 3.12).
- The account, password, security-question, ticket and session logic, the
  language switching, chat history search, slash commands, PDF generation and
  the tests.

## Verification

Run in the cloud workspace, where Dash, Plotly, pymongo and bcrypt cannot be
installed; strict stand-ins were used for those (the Dash one rejects any
component property real Dash rejects). Everything else was real: the
repository code, `pr_dashboard.db`, Flask, pandas, numpy, reportlab, pydantic.

- **397 checks passed**: 284 of the V9/V10 checks re-run against the merged
  package (all of them except the V10 chat-window checks, whose window was
  replaced), plus 113 merge checks:
  - the dashboard layout is identical to V10.1 component by component;
  - all 34 V10.1 dashboard callbacks are registered with identical
    dependencies and identical source code;
  - all 54 other V10.1 functions are byte-identical, except `common_map_year`
    (now shared via `data.py`, same result: 2023) and `encode_image` (logo
    folder);
  - no duplicate ids;
  - all partner callbacks and routes are present;
  - sign-in on and off;
  - sign-up, log-in, cookies and tickets end to end;
  - grounded answers in the partner window, including Aibonito 2022 =
    14.74;
  - the LLM path is unchanged;
  - export of the conversation;
  - municipality reports use the map's values;
  - the "most vulnerable" ranking matches the map;
  - the full MongoDB-outage behaviour above.
- **Partner test suite: 87 of 87 passed**, on both the original branch and
  the merged branch, against an in-memory MongoDB.
- `tools/smoke_test.py` was updated for the new layout. **Run it on a machine
  with the real packages before merging to `main`.**

## Open items

- Choose `OPENAI_MODEL`: the partner default is `gpt-5.6-luna`, and V10 used
  `gpt-5-nano`.
- The OpenAI key reported "out of quota" while the account shows credits.
  The key may belong to a different project or organisation.
- Hugging Face: sign-in works on the Space's direct `*.hf.space` link, not
  inside the embedded huggingface.co page (browsers block the cookie there).
- `/tickets_ui` (admin page) returns an error while MongoDB is down.
