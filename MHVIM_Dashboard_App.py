"""Puerto Rico MHVI dashboard — start the app here.

    python MHVIM_Dashboard_App.py        then open http://localhost:7860

What is where:
    dashboard/   the dashboard: map, right-hand panel, tables, Data Dictionary,
                 Custom Report Builder (the V10.1 version from the usability
                 studies)
    chat/        the AI assistant (history, reports, language, LLM calls)
    auth/        accounts and sign-in;  REQUIRE_LOGIN switches it on or off
    tickets/     "Report an issue"
    mongodb/     where chat history, accounts and tickets are stored
    layout.py    the page around the dashboard: sign-in page, account menu,
                 assistant window, issue form
    callbacks.py what the sign-in, account, ticket and assistant pieces do
    data.py      reads pr_dashboard.db (the data itself is SQLite, not MongoDB)

Settings come from a .env file locally and from the Space's "Variables and
secrets" on Hugging Face — see .env.example and README.md.
"""
import os

import dash

from chat import init_chat_db, register_dashboard_answerer
from data import load_db_metadata, load_data_dictionary
from layout import build_layout
from callbacks import register_callbacks
from auth.routes import register_auth_routes
from tickets.routes import register_ticket_routes
from dashboard import (answer_question, dashboard_children,
                       register_dashboard_callbacks)


app = dash.Dash(__name__, suppress_callback_exceptions=True,
                title='Puerto Rico MHVI Dashboard')
server = app.server  # for gunicorn / hosting platforms

# The dashboard's own styles live in assets/dashboard.css (Dash loads every
# file in assets/ automatically). Only the print rules for the Custom Report
# Builder's "Export report to PDF" stay inline here.
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            @media print {
                body * { visibility: hidden; }
                #custom-reports-modal, #custom-reports-modal * { visibility: visible; }
                #custom-reports-modal { position: absolute; left: 0; top: 0; width: 100%; padding: 0; margin: 0; background: white; z-index: 9999; }
                .no-print { display: none !important; }
                .print-page-break { page-break-after: always; }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Chat database: creates its indexes if MongoDB answers. If it does not, the
# app still starts — the dashboard works, and chat history, sign-in and
# tickets show as temporarily unavailable until the database is back.
init_chat_db()
db_metadata = load_db_metadata()
data_dictionary_df = load_data_dictionary()

# A new layout is built for every page load, so each visitor gets a fresh
# chat session id and the sign-in setting is read when the page opens.
app.layout = lambda: build_layout(dashboard_children)

register_dashboard_callbacks(app)
register_callbacks(app, db_metadata, data_dictionary_df=data_dictionary_df)
register_auth_routes(app.server)
register_ticket_routes(app.server)

# Value questions in the assistant are answered from the dashboard's data
# (the same numbers the chart shows) before anything else is tried.
register_dashboard_answerer(answer_question)


if __name__ == '__main__':
    # Hugging Face Spaces (and most hosts) expect 0.0.0.0 and the port they
    # give in $PORT; 7860 is the Spaces default. Debug mode shows code and
    # reloads on edits — never on a public site, so it is off unless
    # DASH_DEBUG=1 is set.
    app.run(host=os.getenv('HOST', '0.0.0.0'),
            port=int(os.getenv('PORT', '7860')),
            debug=os.getenv('DASH_DEBUG', '0') == '1')
