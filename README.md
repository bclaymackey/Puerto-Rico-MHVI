---
title: Puerto Rico MHVI Dashboard
emoji: 🗺️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Puerto Rico Mental Health Vulnerability Index — Dashboard

AIM-AHEAD project with Grupo Nexos. The goal is to (1) design, from the
literature, a Mental Health Vulnerability Index (MHVI) for Puerto Rico and
(2) deploy an interactive dashboard for exploring the data behind it. (The
project began as an index for minors, "MHVI-M"; that framing has been
dropped. The entry file keeps its old name, MHVIM_Dashboard_App.py.)

The dashboard has a choropleth map of the overall index and its categories
for Puerto Rico's 78 municipalities, trend charts and tables for every
indicator, a Data Dictionary, a Custom Report Builder, and an AI assistant
that answers value questions straight from the dashboard's data. Visitors can
optionally sign in to keep their chat history and report issues.

Built with Plotly Dash. The index data is in the bundled SQLite file
`pr_dashboard.db`; chat history, accounts and support tickets are kept in
MongoDB.

---

## Folder layout

```
MHVIM_Dashboard_App.py   start here: builds the app and runs the server
layout.py                the page around the dashboard: sign-in page, account
                         menu, assistant window, "Report an issue" form
callbacks.py             what those pieces do
data.py                  reads pr_dashboard.db; the map-year rule
pr_dashboard.db          the index data
dashboard/               the dashboard itself (map, side panel, tables, Data
                         Dictionary, Custom Report Builder) — see dashboard/core.py
chat/                    the AI assistant: routing, history, reports, LLM calls
auth/                    accounts and sign-in (auth/policy.py: REQUIRE_LOGIN)
tickets/                 "Report an issue" and the admin page /tickets_ui
mongodb/                 the MongoDB connection and chat-history storage
assets/                  styles and logos (Dash loads this folder automatically)
tests/                   automated tests for accounts, tickets, sessions, LLM
tools/smoke_test.py      pre-flight check — run before pushing to main
tools/check_openai.py    explains why the AI key does or does not work
docs/                    change history; docs/deploy has the Hugging Face sync
Dockerfile               how Hugging Face builds the app
.env.example             every setting, explained — copy it to .env
```

---

## Run it on your computer

You need **Python 3.11 or newer** (the requirements need pandas 3).
Check with `python --version`.

1. Create a virtual environment and install the requirements (once):

   ```
   python -m venv .venv
   .venv\Scripts\activate          (Windows)
   source .venv/bin/activate       (macOS / Linux)
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill it in. Locally, keep
   `AUTH_COOKIE_SECURE=0` (sign-in cookies otherwise need HTTPS).

3. Start it:

   ```
   python MHVIM_Dashboard_App.py
   ```

   then open <http://localhost:7860>.

The dashboard starts even without MongoDB or an AI key: value questions in the
assistant still work, and the rest says "temporarily unavailable".

### Check it before pushing to `main`

```
python tools/smoke_test.py
```

Takes a few seconds, starts no server, needs no key or database. It builds
the page with real Dash, checks every component, callback and property, that
every map category colours all 78 municipalities, that the logos are there,
and that no file outside `.env` contains an API key or database password.
Exit code 0 means it is safe to publish.

The partner tests run with `pytest` against a local MongoDB
(`mongodb://localhost:27017`).

---

## Settings

All settings are environment variables: in `.env` locally, and in the Space's
**Settings → Variables and secrets** on Hugging Face. `.env.example` explains
each one. The main ones:

| Setting | What it does |
|---|---|
| `REQUIRE_LOGIN` | `0` = anyone can use the site, "Sign in" button in the header. `1` = the site opens on the sign-in page. Restart after changing. |
| `MONGODB_URI` | MongoDB Atlas connection string (secret). |
| `LLM_PROVIDER` | `openai` (needed on Hugging Face) or `ollama` (a model on your own computer). |
| `OPENAI_API_KEY` | secret |
| `OPENAI_MODEL` | e.g. `gpt-5-nano` |
| `AUTH_TOKEN_PEPPER` | long random string (secret); keep it fixed once set |
| `AUTH_COOKIE_SECURE` | `0` only for `http://localhost` |
| `ADMIN_EMAILS` | accounts that may open `/tickets_ui` |

### Using a local Ollama model instead of OpenAI

Ollama runs a model on your own computer, free, with no key. It cannot run
inside the free Hugging Face Space, so use it for local work:

```
ollama pull qwen3.5:9b
```

and in `.env`: `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen3.5:9b`.

---

## Publish on Hugging Face Spaces

The block at the top of this file is the Space's configuration (Docker,
port 7860).

1. In the Space's **Settings → Variables and secrets**, add the secrets
   `OPENAI_API_KEY`, `MONGODB_URI`, `AUTH_TOKEN_PEPPER`, and the variables
   `LLM_PROVIDER=openai`, `OPENAI_MODEL`, `REQUIRE_LOGIN=0`.
2. Either upload the files, or let GitHub update the Space automatically on
   every push to `main`: see `docs/deploy/sync-to-huggingface.yml` for the
   steps. **Whatever lands on `main` then goes live**, so merge only tested
   work there.
3. In MongoDB Atlas → **Network Access**, allow `0.0.0.0/0` (Spaces have no
   fixed address); the database user's password protects it.

Sign-in cookies are not kept when the Space is viewed inside the
huggingface.co page (browsers block cookies in that embedded frame). Use the
Space's direct link (`https://<user>-<space>.hf.space`) to sign in; the
dashboard and assistant work in both.

**Never upload or commit a `.env` file** — the repository is public.

---

## Notes on the data

- **The map shows one year for all categories**: the latest year in which
  every municipality has a value in every category (currently 2023), so none
  is left gray. The assistant's "latest" answers and municipality reports use
  the same year, so they always match the map. Charts and tables show every
  year that exists.
- Scores are 0–100 percentile ranks; 100 is the most vulnerable. The method is
  described inside the dashboard (🧮 on any index score).
- Four of the nine subcategories in the methodology do not yet contain data,
  so the Overall score is currently built from the six that do.
- Municipality boundaries are downloaded from GitHub when the app starts, so
  the server needs internet access.

## Change history

`docs/CHANGELOG.md` summarises each version; `docs/change_history/` has the
detailed notes.

---

*The research was supported by AIM-AHEAD Coordinating Center at the
University of North Texas Health Science Center at Fort Worth. This research
was, in part, funded by the National Institutes of Health (NIH) Agreement No.
1OT2OD032581. The views and conclusions contained in this document are those
of the authors and should not be interpreted as representing the official
policies, either expressed or implied, of the NIH.*
