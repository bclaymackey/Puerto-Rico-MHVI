"""Static reference of every real UI feature in this dashboard.

This is the LLM's general-purpose fallback for "how do I / where is / what
does X do" questions that aren't common enough to warrant a dedicated
navigation_guide.py template. It is concatenated into the LLM instructions
as fixed ground truth (see llm_caller.py) — the model is told never to
invent a button, menu, or step that isn't listed here.

Keep this in sync with dashboard/layout.py (the dashboard) and layout.py
(sign-in, settings, tickets, this chat), the same discipline
navigation_guide.py already follows. When a UI feature changes or a new one ships, update the
matching bullet here; only add a bespoke navigation_guide.py template on top
of this if the feature is expected to be a very high-frequency question.
"""

from auth.policy import login_required

_SIGN_IN = (
    "- Signing in: the site opens on a sign-in page; the dashboard, map and this chat appear after signing in. "
    "\"Forgot password?\" leads to a self-service reset using a saved security question — no email needed."
    if login_required() else
    "- Signing in is optional: anyone can use the dashboard and this chat. The \"👤 Sign in\" button at the right-hand end of the header opens the sign-in / sign-up page (with a \"← Back to the dashboard\" link). "
    "Signing in keeps chat history across visits and allows reporting an issue. \"Forgot password?\" leads to a self-service reset using a saved security question — no email needed."
)

SITE_KNOWLEDGE = _SIGN_IN + "\n" + """
- Header, left: a ☰ button opens the "Navigation" panel — "Custom Reports" opens the Custom Report Builder; "Publication", "Data Sources" and "Source Code" are placeholders that do not do anything yet. Next to it: "🧭 How this dashboard is organized" (explains Overall score → Category → Indicator and the right-hand panel) and "ℹ️ Data Dictionary".
- Header, right: the logos, then the account button — "⚙ Settings" when signed in (shows the email, Change password, Security question, "🛟 Report an issue", Sign out).
- Control bar under the header: "Map Category" chooses what colors the map (the Overall MHVI Score or one category's Subcategory Index Score), with a "keep the graph on this category" checkbox; "Go to municipality" is a type-to-search box that opens that municipality's panel; "↺ Reset dashboard" clears every selection (municipalities, category, indicators, year, display mode, projection, custom report) and also starts a new chat.
- A dark bar below the controls always names the active settings (municipality, indicators, Raw or Normalized, projection on/off). While Normalized or the projection is on, an amber alert says so, with "Show raw values" and "Turn off projection" buttons.
- The map shows one year for every category — the latest year in which all 78 municipalities have data (currently 2023), so no municipality is left gray. Charts and tables still show every year that exists.
- Right-hand panel (opens by clicking the map or using "Go to municipality"): "?" explains the panel, ✖ closes it. Removable chips list what is selected. "One / Compare" switches between one municipality and several. The indicator box searches every category at once (a small dropdown beside it narrows the list to one category). Collapsed ⓘ rows give each selected indicator's definition, units and source (and open it in the Data Dictionary); a 🧮 row appears for index scores and shows how the score is built. "Raw / Normalized 0–100", "1 chart / Split axes" and "Project 4 future years" (a Holt linear-trend projection, shown dashed and labelled as predicted) change the chart. "Values for year" lists exact values for one year as text, with averages across municipalities — no hovering needed. Under the chart: "⬇ PNG", "⬇ CSV" and "➕ Add to report". The table "Data behind this chart" carries raw value, normalized value and observed/projected status for every row; ⤢ opens it full page, and it can be sorted, filtered and exported.
- Data Dictionary ("ℹ️ Data Dictionary" in the header): a searchable glossary of indicator names and definitions with a category filter; selecting a row shows its full definition with a "⧉ Copy definition" button. It does not yet cover every indicator.
- Custom Report Builder (☰ → "Custom Reports", or "➕ Add to report" under the chart, which sends the exact graph with its settings): each element is a "Line Graph" or "Data Table" with its own municipalities, category, indicator and options ("Normalized 0–100", "Include projection"). "+ Add blank element" adds another; "🖨 Export report to PDF" opens the browser's print dialog (choose "Save as PDF") — it is not a server-generated file.
- Report an issue / support ticket (signed-in users, ⚙ Settings → "🛟 Report an issue"): choose a category (Technical, Account, Data, Other), write a subject and a description, then Submit. A team member follows up by email; there is no live chat support.
- The AI chat widget (this chat): a launcher button bottom-left opens a resizable popup. Its "⋮" menu has: a 🌐 button to switch the chat language instantly, "Chat History" (search/rename/delete past conversations — signed-in users only), "＋ New Chat", "⛶ Fit Window" to resize, and "Download Chat PDF" (the full conversation transcript). Typed slash-commands also work: /new (new chat), /spanish or /english (switch language), /delete (erase all chat history, asks to confirm first), /cancel, and /name <name> to set a preferred name. Questions about a value ("What is Arecibo's overall score in 2022?", "average of the selected municipalities") are answered straight from the dashboard's data, marked "✓ Read from dashboard data", with the rows used and a "View these values in the graph" button.
- There are three separate "download as PDF" features — do not confuse them: (1) chat menu "Download Chat PDF" (or asking this chat to "export this conversation") downloads the whole conversation transcript; (2) asking this chat to "generate a report for [municipality]" produces a single AI-written narrative PDF for one municipality, with a "Download report" button in that reply; (3) the Custom Report Builder's "🖨 Export report to PDF" (above) is a browser print-to-PDF of a report the user builds themselves.
""".strip()
