from datetime import datetime
import uuid

import dash
from dash import Input, Output, State, dcc, html, ALL
from chat import (
    build_pdf_bytes,
    consume_report,
    delete_all_user_data,
    delete_session,
    get_history_for_display,
    get_session_title,
    list_user_sessions,
    process_chat_message,
    rename_session,
    search_user_conversations,
    set_user_name,
)

from flask import after_this_request, request

from auth.routes import current_user_id, COOKIE, _cookie_secure
from auth.core import (
    login as auth_login,
    signup as auth_signup,
    create_session,
    revoke_session,
    get_public_user,
    change_password,
    set_security_question,
    get_security_question,
    reset_password_with_answer,
)
from mongodb.chat_dal import get_name_prompted, set_name_prompted, get_user_name

from functools import wraps

from pymongo.errors import PyMongoError

from auth.policy import login_required
from mongodb.client import is_available as mongo_available, mark_unavailable
from dashboard import grounded_bubble


# Shown wherever a feature needs the chat database and it cannot be reached.
_UNAVAILABLE = {
    'en': 'temporarily unavailable',
    'es': 'no disponible temporalmente',
}


class _MongoSafeApp:
    """Wraps the Dash app so that a MongoDB failure inside any callback below
    leaves the page as it was instead of showing an error, and the next few
    requests skip the database at once (see mongodb/client.py). The dashboard
    itself never touches MongoDB, so it keeps working throughout."""

    def __init__(self, app):
        self._app = app

    def callback(self, *args, **kwargs):
        register = self._app.callback(*args, **kwargs)

        def decorator(fn):
            @wraps(fn)
            def guarded(*a, **k):
                try:
                    return fn(*a, **k)
                except PyMongoError as exc:
                    mark_unavailable()
                    print(f"[{fn.__name__}] MongoDB unavailable: {exc}")
                    raise dash.exceptions.PreventUpdate
            return register(guarded)
        return decorator

    def __getattr__(self, name):  # clientside_callback, server, …
        return getattr(self._app, name)


def register_callbacks(app: dash.Dash, db_metadata: dict = None, data_dictionary_df=None) -> None:
    """Sign-in, account, ticket and AI-assistant callbacks.

    The dashboard's own callbacks are registered by
    dashboard.register_dashboard_callbacks(). db_metadata and
    data_dictionary_df are no longer needed here (they fed the older V6
    dashboard callbacks) and are kept only so existing calls still work.
    """
    app = _MongoSafeApp(app)

    # Resolve the logged-in user id from the auth session cookie on each page load.
    # This replaces the old anonymous browser-UUID identity: user_id now comes from
    # the MongoDB account (or None when not logged in, which triggers the auth gate).
    @app.callback(
        Output('chat-user-id', 'data'),
        Input('chat-user-id', 'modified_timestamp'),
    )
    def resolve_chat_user_id(_):
        if not mongo_available():
            return None
        return current_user_id()

    def _attach_session_cookie(raw_token: str, remember: bool):
        """Queue a Set-Cookie header on the current callback's HTTP response."""
        max_age = 60 * 60 * 24 * (30 if remember else 1)

        @after_this_request
        def _set(response):
            response.set_cookie(
                COOKIE, raw_token, httponly=True, secure=_cookie_secure(),
                samesite='Lax', max_age=max_age,
            )
            return response

    # Full-page gate: show the login page and hide the app body when logged out;
    # reveal the app and hide the login page once authenticated.
    #   REQUIRE_LOGIN on  -> the site lands on the login page for anonymous
    #                        visitors (the original behaviour).
    #   REQUIRE_LOGIN off -> the dashboard is open to everyone; the login page
    #                        appears only after clicking "Sign in".
    # If MongoDB cannot be reached nobody can sign in, so the dashboard is shown
    # rather than a login form that cannot work.
    @app.callback(
        [Output('login-page', 'style'),
         Output('app-body', 'style')],
        [Input('chat-user-id', 'data'),
         Input('login-requested', 'data')],
        [State('login-page', 'style'),
         State('app-body', 'style')],
    )
    def toggle_site_gate(user_id, login_requested, login_style, body_style):
        login_style = dict(login_style or {})
        body_style = dict(body_style or {})
        if user_id:
            show_login = False
        elif login_required():
            show_login = mongo_available()
        else:
            show_login = bool(login_requested) and mongo_available()
        if not show_login:
            login_style['display'] = 'none'
            body_style['display'] = 'block'
        else:
            login_style['display'] = 'flex'
            body_style['display'] = 'none'
        return login_style, body_style

    # Optional sign-in: the header button opens the login page for a visitor
    # who is not signed in; "Back to the dashboard" closes it; signing in or
    # out resets it.
    @app.callback(
        Output('login-requested', 'data'),
        [Input('account-menu-btn', 'n_clicks'),
         Input('login-back-link', 'n_clicks'),
         Input('chat-user-id', 'data')],
        prevent_initial_call=True,
    )
    def request_login(_menu_clicks, _back_clicks, user_id):
        trigger = dash.ctx.triggered_id
        if trigger == 'account-menu-btn':
            return not user_id
        return False

    # The header button: "⚙ Settings" when signed in, "Sign in" otherwise.
    @app.callback(
        [Output('account-menu-btn', 'children'),
         Output('account-menu-btn', 'title')],
        Input('chat-user-id', 'data'),
    )
    def account_button_label(user_id):
        if user_id:
            return '⚙ Settings', 'Account settings, report an issue, sign out'
        if not mongo_available():
            return ('👤 Sign in', 'Signing in is ' + _UNAVAILABLE['en'] +
                    '. The dashboard and the assistant still work.')
        return '👤 Sign in', 'Sign in to keep your chat history and report issues'

    # Toggle the form between login and signup: show/hide the confirm field, swap
    # the button label and the prompt text.
    @app.callback(
        [Output('auth-mode', 'data'),
         Output('auth-title', 'children'),
         Output('auth-submit-btn', 'children'),
         Output('auth-confirm', 'style'),
         Output('auth-toggle-prompt', 'children'),
         Output('auth-toggle-link', 'children'),
         Output('auth-error', 'children', allow_duplicate=True)],
        Input('auth-toggle-link', 'n_clicks'),
        State('auth-mode', 'data'),
        prevent_initial_call=True,
    )
    def toggle_auth_mode(_clicks, mode):
        from layout import _AUTH_INPUT_STYLE
        going_signup = (mode or 'login') == 'login'
        confirm_style = dict(_AUTH_INPUT_STYLE)
        confirm_style['display'] = 'block' if going_signup else 'none'
        if going_signup:
            return ('signup', 'Create an account', 'Sign up', confirm_style,
                    'Have an account? ', 'Log in', '')
        return ('login', 'Sign in', 'Log in', confirm_style,
                'No account? ', 'Sign up', '')

    # Submit login or signup. On success, set the session cookie and populate
    # chat-user-id (which hides the overlay via the gate callback above).
    @app.callback(
        [Output('chat-user-id', 'data', allow_duplicate=True),
         Output('auth-error', 'children', allow_duplicate=True)],
        Input('auth-submit-btn', 'n_clicks'),
        [State('auth-mode', 'data'),
         State('auth-email', 'value'),
         State('auth-password', 'value'),
         State('auth-confirm', 'value')],
        prevent_initial_call=True,
    )
    def submit_auth(n_clicks, mode, email, password, confirm):
        if not n_clicks:
            return dash.no_update, dash.no_update
        if not mongo_available():
            return dash.no_update, ('Signing in is ' + _UNAVAILABLE['en'] +
                                    '. Please try again in a few minutes.')
        email = (email or '').strip()
        password = password or ''
        if (mode or 'login') == 'signup':
            if password != (confirm or ''):
                return dash.no_update, 'Passwords do not match.'
            user, err = auth_signup(email, password)
        else:
            user, err = auth_login(email, password)
        if err:
            return dash.no_update, err
        raw = create_session(user['userId'], remember=True)
        _attach_session_cookie(raw, remember=True)
        return user['userId'], ''

    # Sign out: revoke the server-side session, clear the cookie, and drop the
    # user id (which re-shows the login page via the gate).
    @app.callback(
        Output('chat-user-id', 'data', allow_duplicate=True),
        Input('sign-out-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def sign_out(n_clicks):
        if not n_clicks:
            return dash.no_update
        revoke_session(request.cookies.get(COOKIE))

        @after_this_request
        def _clear(response):
            response.delete_cookie(COOKIE)
            return response

        return None

    # Open/close the account settings panel (gear button).
    @app.callback(
        Output('account-panel', 'style'),
        Input('account-menu-btn', 'n_clicks'),
        [State('account-panel', 'style'),
         State('chat-user-id', 'data')],
        prevent_initial_call=True,
    )
    def toggle_account_panel(n_clicks, style, user_id):
        if not user_id:  # not signed in: the button opens the login page instead
            return {**(style or {}), 'display': 'none'}
        style = dict(style or {})
        style['display'] = 'none' if style.get('display') == 'block' else 'block'
        return style

    # Show the logged-in account's email at the top of the settings panel.
    @app.callback(
        Output('account-email', 'children'),
        Input('chat-user-id', 'data'),
    )
    def show_account_email(user_id):
        if not user_id:
            return ''
        user = get_public_user(user_id)
        return user['email'] if user else ''

    # Change password from the account panel.
    @app.callback(
        [Output('account-pw-msg', 'children'),
         Output('account-current-pw', 'value'),
         Output('account-new-pw', 'value')],
        Input('account-change-pw-btn', 'n_clicks'),
        [State('chat-user-id', 'data'),
         State('account-current-pw', 'value'),
         State('account-new-pw', 'value')],
        prevent_initial_call=True,
    )
    def change_pw(n_clicks, user_id, current, new):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update
        if not user_id:
            return 'Please log in again.', dash.no_update, dash.no_update
        ok, err = change_password(user_id, current or '', new or '')
        if ok:
            return 'Password updated.', '', ''
        return err, dash.no_update, dash.no_update

    # Save an optional security question + answer from the account panel.
    @app.callback(
        [Output('account-secq-msg', 'children'),
         Output('account-seca', 'value')],
        Input('account-secq-btn', 'n_clicks'),
        [State('chat-user-id', 'data'),
         State('account-secq', 'value'),
         State('account-seca', 'value')],
        prevent_initial_call=True,
    )
    def save_security_question(n_clicks, user_id, question, answer):
        if not n_clicks:
            return dash.no_update, dash.no_update
        if not user_id:
            return 'Please log in again.', dash.no_update
        ok, err = set_security_question(user_id, question or '', answer or '')
        if ok:
            return 'Security question saved.', ''  # clear the answer field
        return err, dash.no_update

    # Show/hide the forgot-password card (link opens it, "back" closes it).
    @app.callback(
        Output('forgot-card', 'style'),
        [Input('forgot-link', 'n_clicks'),
         Input('forgot-back', 'n_clicks')],
        State('forgot-card', 'style'),
        prevent_initial_call=True,
    )
    def toggle_forgot_card(open_clicks, back_clicks, style):
        style = dict(style or {})
        style['display'] = 'none' if dash.ctx.triggered_id == 'forgot-back' else 'block'
        return style

    # Step 1: look up the account's security question by email.
    @app.callback(
        [Output('forgot-question', 'children'),
         Output('forgot-step2', 'style'),
         Output('forgot-msg', 'children', allow_duplicate=True)],
        Input('forgot-lookup-btn', 'n_clicks'),
        State('forgot-email', 'value'),
        prevent_initial_call=True,
    )
    def forgot_lookup(n_clicks, email):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update
        question = get_security_question(email or '')
        if not question:
            # Same message whether the email is unknown or has no question set,
            # so this can't be used to probe which emails have accounts.
            return '', {'display': 'none'}, (
                'No security question is set for that email. Ask an admin to reset it.'
            )
        return f'Q: {question}', {'display': 'block', 'marginTop': '14px'}, ''

    # Step 2: verify the answer and set a new password.
    @app.callback(
        Output('forgot-msg', 'children', allow_duplicate=True),
        Input('forgot-reset-btn', 'n_clicks'),
        [State('forgot-email', 'value'),
         State('forgot-answer', 'value'),
         State('forgot-newpw', 'value')],
        prevent_initial_call=True,
    )
    def forgot_reset(n_clicks, email, answer, new_pw):
        if not n_clicks:
            return dash.no_update
        ok, err = reset_password_with_answer(email or '', answer or '', new_pw or '')
        if ok:
            return 'Password reset. You can now sign in with your new password.'
        return err

    # The dashboard itself (map, side panel, tables, Data Dictionary, Custom
    # Report Builder) is registered separately from dashboard/callbacks.py.
    # The older V6 versions of those callbacks that used to live here were
    # removed when the V10.1 dashboard was merged in.

    @app.callback(
        Output('chat-window-state', 'data'),
        [Input('chat-btn', 'n_clicks'),
         Input('chat-fit-window-btn', 'n_clicks')],
        State('chat-window-state', 'data'),
        prevent_initial_call=True,
    )
    def update_chat_window_state(open_clicks, fit_clicks, window_state):
        state = {'open': False, 'fit': False, **(window_state or {})}
        trigger_id = dash.ctx.triggered_id
        if trigger_id == 'chat-btn' and open_clicks:
            state['open'] = not bool(state.get('open', False))
            return state
        if trigger_id == 'chat-fit-window-btn' and fit_clicks:
            state['fit'] = not bool(state.get('fit', False))
            return state
        return dash.no_update

    app.clientside_callback(
        """
        function(windowState, windowSize) {
            var state = windowState || {open: false, fit: false};
            var size = windowSize || {width: 300, height: 400};
            var width = Math.min(window.innerWidth * 0.9, Math.max(280, Number(size.width) || 300));
            var height = Math.min(window.innerHeight * 0.85, Math.max(350, Number(size.height) || 400));
            return {
                display: state.open ? 'flex' : 'none',
                position: 'fixed',
                top: state.fit ? '20px' : 'auto',
                right: state.fit ? '20px' : 'auto',
                bottom: state.fit ? '20px' : '80px',
                left: state.fit ? '20px' : '20px',
                width: state.fit ? 'auto' : width + 'px',
                height: state.fit ? 'auto' : height + 'px',
                minWidth: '280px',
                minHeight: '350px',
                maxWidth: state.fit ? 'none' : '90vw',
                maxHeight: state.fit ? 'none' : '85vh',
                backgroundColor: 'white',
                border: '1px solid #ccc',
                borderRadius: '10px',
                boxShadow: '0 4px 10px rgba(0,0,0,0.2)',
                zIndex: '1000',
                padding: '10px',
                flexDirection: 'column',
                boxSizing: 'border-box'
            };
        }
        """,
        Output('chat-popup', 'style'),
        [Input('chat-window-state', 'data'),
         Input('chat-window-size', 'data')],
    )

    @app.callback(
        Output('chat-resize-handle', 'style'),
        Input('chat-window-state', 'data'),
    )
    def sync_chat_resize_handle(window_state):
        style = {
            'position': 'absolute',
            'top': '4px',
            'right': '6px',
            'width': '28px',
            'height': '28px',
            'display': 'block',
            'cursor': 'nesw-resize',
            'zIndex': '1001',
            'userSelect': 'none',
        }
        if (window_state or {}).get('fit'):
            style['display'] = 'none'
        return style

    app.clientside_callback(
        """
        function(id) {
            if (window._chatResizeInit) { return window.dash_clientside.no_update; }
            var handle = document.getElementById('chat-resize-handle');
            var popup = document.getElementById('chat-popup');
            if (!handle || !popup) { return window.dash_clientside.no_update; }
            window._chatResizeInit = true;

            var dragging = false;
            var startX, startY, startW, startH;

            handle.addEventListener('mousedown', function (e) {
                if (handle.style.display === 'none') { return; }
                dragging = true;
                startX = e.clientX;
                startY = e.clientY;
                var rect = popup.getBoundingClientRect();
                startW = rect.width;
                startH = rect.height;
                e.preventDefault();
                e.stopPropagation();
            });

            document.addEventListener('mousemove', function (e) {
                if (!dragging) { return; }
                var dx = e.clientX - startX;
                var dy = e.clientY - startY;
                var newW = Math.min(window.innerWidth * 0.9, Math.max(280, startW + dx));
                var newH = Math.min(
                    window.innerHeight * 0.85,
                    Math.max(350, startH - dy)
                );
                popup.style.width = newW + 'px';
                popup.style.height = newH + 'px';
            });

            document.addEventListener('mouseup', function () {
                if (!dragging) { return; }
                dragging = false;
                var rect = popup.getBoundingClientRect();
                window.dash_clientside.set_props('chat-window-size', {
                    data: {width: Math.round(rect.width), height: Math.round(rect.height)}
                });
            });

            return window.dash_clientside.no_update;
        }
        """,
        Output('chat-resize-handle', 'title'),
        Input('chat-resize-handle', 'id'),
    )

    @app.callback(
        Output('chat-menu-open', 'data'),
        [Input('chat-menu-btn', 'n_clicks'),
         Input('chat-language-toggle-btn', 'n_clicks'),
         Input('chat-sessions-btn', 'n_clicks'),
         Input('chat-new-session-btn', 'n_clicks'),
         Input('chat-fit-window-btn', 'n_clicks'),
         Input('download-pdf-btn', 'n_clicks')],
        State('chat-menu-open', 'data'),
        prevent_initial_call=True,
    )
    def toggle_chat_menu(menu_clicks, lang_clicks, sessions_clicks, new_clicks, fit_clicks, pdf_clicks, is_open):
        if dash.ctx.triggered_id == 'chat-menu-btn':
            return not bool(is_open)
        return False

    @app.callback(
        Output('chat-menu-dropdown', 'style'),
        Input('chat-menu-open', 'data'),
    )
    def sync_chat_menu_style(is_open):
        return {
            'display': 'flex' if is_open else 'none',
            'position': 'absolute',
            'top': '100%',
            'right': '0',
            'marginTop': '4px',
            'minWidth': '170px',
            'flexDirection': 'column',
            'backgroundColor': 'white',
            'borderRadius': '10px',
            'boxShadow': '0 12px 24px rgba(22, 7, 39, 0.18)',
            'overflow': 'hidden',
            'zIndex': '1003',
        }

    app.clientside_callback(
        """
        function(id) {
            if (window._chatMenuOutsideClickInit) { return window.dash_clientside.no_update; }
            window._chatMenuOutsideClickInit = true;

            document.addEventListener('click', function (e) {
                var btn = document.getElementById('chat-menu-btn');
                var dropdown = document.getElementById('chat-menu-dropdown');
                if (!btn || !dropdown || dropdown.style.display === 'none') { return; }
                if (btn.contains(e.target) || dropdown.contains(e.target)) { return; }
                window.dash_clientside.set_props('chat-menu-open', {data: false});
            });

            return window.dash_clientside.no_update;
        }
        """,
        Output('chat-menu-btn', 'title'),
        Input('chat-menu-btn', 'id'),
    )

    # Show the transient "Downloaded!" overlay (blurred over the chat window)
    # after a chat PDF download. Report downloads use the button label +
    # re-download confirmation modal instead — see export_report_pdf below.
    app.clientside_callback(
        """
        function(chatState) {
            if (!chatState || !chatState.downloaded) {
                return window.dash_clientside.no_update;
            }
            var el = document.getElementById('download-overlay');
            if (el) {
                el.classList.add('visible');
                setTimeout(function () { el.classList.remove('visible'); }, 2200);
            }
            return chatState.label || 'Downloaded!';
        }
        """,
        Output('download-overlay-text', 'children'),
        Input('chat-download-state', 'data'),
        prevent_initial_call=True,
    )

    def _format_message_timestamp(timestamp_value):
        if not timestamp_value:
            return ''
        try:
            return datetime.fromisoformat(timestamp_value).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return str(timestamp_value).replace('T', ' ')[:16]

    def _bubble_container(
        *,
        body_children,
        role,
        language='en',
        timestamp=None,
        message_id=None,
        highlight=False,
        copy_text=None,
    ):
        is_user = role == 'user'
        meta_children = []
        if timestamp:
            meta_children.append(
                html.Span(
                    _format_message_timestamp(timestamp),
                    style={'fontSize': '10px', 'opacity': '0.72'},
                )
            )
        if copy_text and not is_user:
            meta_children.append(
                dcc.Clipboard(
                    content=copy_text,
                    title='Copiar mensaje' if language == 'es' else 'Copy message',
                    style={
                        'fontSize': '12px',
                        'cursor': 'pointer',
                        'color': '#4b0082',
                    },
                )
            )

        bubble_children = []
        if meta_children:
            bubble_children.append(
                html.Div(
                    meta_children,
                    style={
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'space-between',
                        'marginBottom': '6px',
                        'gap': '8px',
                    },
                )
            )
        bubble_children.extend(body_children)

        bubble_style = {
            'padding': '10px 12px',
            'borderRadius': (
                '16px 16px 4px 16px'
                if is_user
                else '16px 16px 16px 4px'
            ),
            'maxWidth': '82%',
            'wordWrap': 'break-word',
            'whiteSpace': 'pre-wrap',
            'backgroundColor': '#4b0082' if is_user else '#f5f0fb',
            'color': 'white' if is_user else '#2f2540',
            'border': '1px solid #d9c7f0' if not is_user else 'none',
            'boxShadow': (
                '0 0 0 2px rgba(75, 0, 130, 0.18)'
                if highlight
                else 'none'
            ),
        }

        container_kwargs = {
            'style': {
                'display': 'flex',
                'justifyContent': 'flex-end' if is_user else 'flex-start',
                'marginBottom': '8px',
            },
        }
        if message_id:
            container_kwargs['id'] = f'chat-message-{message_id}'

        return html.Div(
            html.Div(bubble_children, style=bubble_style),
            **container_kwargs,
        )

    def _user_bubble(text, timestamp=None, message_id=None, language='en', highlight=False):
        return _bubble_container(
            body_children=[html.Div(text)],
            role='user',
            language=language,
            timestamp=timestamp,
            message_id=message_id,
            highlight=highlight,
        )

    def _ai_bubble(text, timestamp=None, message_id=None, language='en', highlight=False):
        return _bubble_container(
            body_children=[html.Div(text)],
            role='assistant',
            language=language,
            timestamp=timestamp,
            message_id=message_id,
            highlight=highlight,
            copy_text=text,
        )

    # v1: one outstanding report at a time. The button id is fixed; clicking
    # always downloads whichever report is currently pinned in `pending-report`.
    def _report_bubble(message, language, timestamp=None, message_id=None, highlight=False):
        btn_label = 'Descargar informe' if language == 'es' else 'Download report'
        return _bubble_container(
            body_children=[
                html.Div(message, style={'marginBottom': '8px'}),
                html.Button(
                    btn_label,
                    id='download-report-btn',
                    n_clicks=0,
                    style={
                        'fontSize': '12px',
                        'padding': '6px 12px',
                        'border': '1px solid #4b0082',
                        'borderRadius': '6px',
                        'background': '#4b0082',
                        'color': 'white',
                        'cursor': 'pointer',
                    },
                ),
            ],
            role='assistant',
            language=language,
            timestamp=timestamp,
            message_id=message_id,
            highlight=highlight,
            copy_text=message,
        )

    def _typing_bubble():
        dot_style = {
            'width': '8px', 'height': '8px',
            'backgroundColor': '#888',
            'borderRadius': '50%',
            'display': 'inline-block',
            'margin': '0 2px',
        }
        return html.Div(
            html.Div(
                [
                    html.Span(className='typing-dot typing-dot-1', style=dot_style),
                    html.Span(className='typing-dot typing-dot-2', style=dot_style),
                    html.Span(className='typing-dot typing-dot-3', style=dot_style),
                ],
                style={
                    'backgroundColor': '#f0f0f0',
                    'padding': '10px 14px',
                    'borderRadius': '16px 16px 16px 4px',
                    'display': 'inline-block',
                }
            ),
            id='typing-indicator',
            style={'display': 'flex', 'justifyContent': 'flex-start', 'marginBottom': '6px'}
        )

    def _is_typing_indicator(child):
        if isinstance(child, dict):
            return child.get('props', {}).get('id') == 'typing-indicator'
        return getattr(child, 'id', None) == 'typing-indicator'

    def _welcome_bubble(language):
        if language == 'es':
            header = "¡Hola! 👋 Soy tu asistente de IA."
            body = (
                "Puedes hacerme preguntas sobre los datos de vulnerabilidad de "
                "salud mental de Puerto Rico, tendencias por municipio, factores "
                "de riesgo comunitarios y determinantes sociales de la salud."
            )
            try_label = "Prueba con preguntas como:"
            examples = [
                '"¿Cuál es el puntaje general de Arecibo?"',
                '"¿Puedes darme un informe general sobre Arecibo?"',
                '"¿Cómo cambio el mapa para mostrar las puntuaciones educativas?"',
            ]
        else:
            header = "Hello! 👋 I'm your AI assistant."
            body = (
                "You can ask me questions about Puerto Rico's mental health "
                "vulnerability data, municipality trends, community risk "
                "factors, and social determinants of health."
            )
            try_label = "Try questions like:"
            examples = [
                '"What is the overall score for Arecibo?"',
                '"Can you give me an overall report for Arecibo?"',
                '"How do I change the map to education scores?"',
            ]

        return html.Div(
            html.Div(
                [
                    html.Div(header, style={'marginBottom': '6px', 'fontWeight': '600'}),
                    html.Div(body, style={'marginBottom': '6px'}),
                    html.Div(try_label, style={'marginBottom': '2px'}),
                    html.Ul(
                        [html.Li(ex) for ex in examples],
                        style={'paddingLeft': '18px', 'margin': '0 0 6px 0'}
                    ),
                ],
                style={
                    'backgroundColor': '#f0f0f0', 'color': '#333',
                    'padding': '8px 12px',
                    'borderRadius': '16px 16px 16px 4px',
                    'maxWidth': '90%', 'wordWrap': 'break-word',
                    'fontSize': '13px', 'lineHeight': '1.4'
                }
            ),
            style={
                'display': 'flex', 'justifyContent': 'flex-start',
                'marginBottom': '6px'
            }
        )

    def _render_history_messages(history, language, highlight_message_id=None):
        messages = []
        for item in history:
            message_id = item.get('id')
            highlighted = bool(highlight_message_id and message_id == highlight_message_id)
            if item.get('role') == 'user':
                messages.append(
                    _user_bubble(
                        item.get('text', ''),
                        timestamp=item.get('timestamp'),
                        message_id=message_id,
                        language=language,
                        highlight=highlighted,
                    )
                )
            else:
                messages.append(
                    _ai_bubble(
                        item.get('text', ''),
                        timestamp=item.get('timestamp'),
                        message_id=message_id,
                        language=language,
                        highlight=highlighted,
                    )
                )
        return messages or [_welcome_bubble(language)]

    def _session_meta_label(session, language):
        timestamp_value = session.get('updated_at') or session.get('created_at')
        timestamp_label = _format_message_timestamp(timestamp_value)
        message_label = 'mensajes' if language == 'es' else 'messages'
        return f"{timestamp_label} · {session.get('message_count', 0)} {message_label}"

    def _render_session_rows(sessions, active_session_id, language, search_value,
                             empty_text=None):
        if not sessions:
            if empty_text is None:
                empty_text = 'No saved chats.' if language != 'es' else 'No hay chats guardados.'
            return [
                html.Div(
                    empty_text,
                    style={
                        'padding': '10px 8px',
                        'borderRadius': '10px',
                        'background': 'rgba(255,255,255,0.08)',
                        'color': '#efe7f8',
                        'fontSize': '12px',
                    },
                )
            ]

        rows = []
        has_search = bool((search_value or '').strip())
        for session in sessions:
            is_active = session['id'] == active_session_id
            preview = session.get('match_preview') if has_search else None
            meta_text = _session_meta_label(session, language)
            body_children = [
                html.Div(
                    session['title'][:80],
                    style={
                        'fontWeight': '700',
                        'fontSize': '13px',
                        'color': '#2d1447',
                        'marginBottom': '4px',
                    },
                ),
            ]
            if preview:
                body_children.append(
                    html.Div(
                        preview[:120],
                        style={
                            'fontSize': '11px',
                            'color': '#5b486f',
                            'marginBottom': '5px',
                        },
                    )
                )
            body_children.append(
                html.Div(
                    meta_text,
                    style={'fontSize': '11px', 'color': '#755f8e'},
                )
            )

            rows.append(
                html.Div(
                    [
                        html.Button(
                            body_children,
                            id={
                                'type': 'chat-session-button',
                                'session_id': session['id'],
                                'message_id': session.get('match_message_id') or 0,
                            },
                            n_clicks=0,
                            style={
                                'flex': '1',
                                'padding': '10px',
                                'textAlign': 'left',
                                'border': 'none',
                                'background': 'transparent',
                                'cursor': 'pointer',
                            },
                        ),
                        html.Div(
                            [
                                html.Button(
                                    'Rename' if language != 'es' else 'Renombrar',
                                    id={
                                        'type': 'chat-session-rename-btn',
                                        'session_id': session['id'],
                                    },
                                    n_clicks=0,
                                    title='Rename conversation' if language != 'es' else 'Renombrar conversación',
                                    style={
                                        'fontSize': '11px',
                                        'padding': '5px 7px',
                                        'borderRadius': '8px',
                                        'border': '1px solid #d2c1e8',
                                        'background': 'white',
                                        'color': '#4b0082',
                                        'cursor': 'pointer',
                                    },
                                ),
                                html.Button(
                                    'Delete' if language != 'es' else 'Borrar',
                                    id={
                                        'type': 'chat-session-delete-btn',
                                        'session_id': session['id'],
                                    },
                                    n_clicks=0,
                                    title='Delete conversation' if language != 'es' else 'Borrar conversación',
                                    style={
                                        'fontSize': '11px',
                                        'padding': '5px 7px',
                                        'borderRadius': '8px',
                                        'border': '1px solid #efc3cd',
                                        'background': '#fff6f8',
                                        'color': '#a43d56',
                                        'cursor': 'pointer',
                                    },
                                ),
                            ],
                            style={
                                'display': 'flex',
                                'flexDirection': 'column',
                                'gap': '6px',
                                'padding': '10px 10px 10px 0',
                            },
                        ),
                    ],
                    style={
                        'display': 'flex',
                        'alignItems': 'stretch',
                        'marginBottom': '8px',
                        'borderRadius': '12px',
                        'background': '#f5effd' if is_active else 'rgba(255,255,255,0.95)',
                        'border': '1px solid #cbb4e8' if is_active else '1px solid rgba(255,255,255,0.3)',
                        'boxShadow': '0 6px 14px rgba(19, 8, 35, 0.08)',
                    },
                )
            )
        return rows

    app.clientside_callback(
        """
        function(target) {
            if (!target || !target.message_id) {
                return window.dash_clientside.no_update;
            }
            window.setTimeout(function() {
                var node = document.getElementById('chat-message-' + target.message_id);
                if (node) {
                    node.scrollIntoView({behavior: 'smooth', block: 'center'});
                }
            }, 80);
            return '';
        }
        """,
        Output('chat-scroll-anchor', 'children'),
        Input('chat-scroll-target', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('chat-sessions-open', 'data'),
        Input('chat-sessions-btn', 'n_clicks'),
        State('chat-sessions-open', 'data'),
        prevent_initial_call=True,
    )
    def toggle_chat_sessions(n_clicks, is_open):
        if not n_clicks:
            return dash.no_update
        return not bool(is_open)

    @app.callback(
        [Output('chat-sessions-panel', 'style'),
         Output('chat-messages-container', 'style'),
         Output('chat-input-row', 'style')],
        Input('chat-sessions-open', 'data'),
    )
    def sync_sessions_panel_layout(is_open):
        if is_open:
            return (
                {
                    'display': 'flex',
                    'flex': '1',
                    'flexDirection': 'column',
                    'minHeight': '0',
                    'marginBottom': '10px',
                    'padding': '12px',
                    'borderRadius': '12px',
                    'background': 'linear-gradient(180deg, #33104e 0%, #5b2c83 100%)',
                    'boxShadow': '0 12px 24px rgba(22, 7, 39, 0.18)',
                },
                {'display': 'none'},
                {'display': 'none'},
            )

        return (
            {'display': 'none'},
            {
                'display': 'flex',
                'flex': '1',
                'minHeight': '0',
                'marginBottom': '10px',
            },
            {
                'display': 'flex',
                'alignItems': 'center',
                'border': '1px solid #ddd',
                'borderRadius': '20px',
                'padding': '5px 10px',
                'backgroundColor': '#f9f9f9',
            },
        )

    @app.callback(
        Output('chat-sessions-list', 'children'),
        [Input('chat-sessions-open', 'data'),
         Input('chat-history-tick', 'data'),
         Input('chat-session-search', 'value'),
         Input('chat-language', 'data')],
        [State('chat-user-id', 'data'),
         State('chat-session-id', 'data')],
    )
    def render_chat_sessions(is_open, _tick, search_value, language, user_id, active_session_id):
        if not is_open:
            return dash.no_update
        language = language or 'en'
        # Chat history belongs to an account: say so instead of an empty list.
        if not mongo_available():
            note = ('El historial de chats no está disponible temporalmente.'
                    if language == 'es' else
                    'Chat history is temporarily unavailable.')
            return _render_session_rows([], active_session_id, language, '', note)
        if not user_id:
            note = ('Inicia sesión para guardar y ver tu historial de chats.'
                    if language == 'es' else
                    'Sign in to save and see your chat history.')
            return _render_session_rows([], active_session_id, language, '', note)
        sessions = (
            search_user_conversations(user_id, search_value or '', language=language)
            if (search_value or '').strip()
            else list_user_sessions(user_id, language)
        )
        return _render_session_rows(sessions, active_session_id, language, search_value or '')

    @app.callback(
        [Output('chat-session-rename-row', 'style'),
         Output('chat-session-rename-input', 'value')],
        Input('chat-rename-session-id', 'data'),
        State('chat-language', 'data'),
    )
    def sync_rename_row(session_id, language):
        if not session_id:
            return {'display': 'none'}, ''
        return (
            {
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
            },
            get_session_title(session_id, language or 'en'),
        )

    @app.callback(
        Output('chat-rename-session-id', 'data'),
        Input({'type': 'chat-session-rename-btn', 'session_id': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def open_rename_session(clicks):
        triggered = dash.ctx.triggered_id
        click_value = dash.ctx.triggered[0].get('value') if dash.ctx.triggered else 0
        if not isinstance(triggered, dict) or not click_value:
            return dash.no_update
        return triggered.get('session_id')

    @app.callback(
        [Output('chat-rename-session-id', 'data', allow_duplicate=True),
         Output('chat-history-tick', 'data', allow_duplicate=True)],
        [Input('chat-session-rename-save-btn', 'n_clicks'),
         Input('chat-session-rename-cancel-btn', 'n_clicks')],
        [State('chat-rename-session-id', 'data'),
         State('chat-session-rename-input', 'value'),
         State('chat-language', 'data'),
         State('chat-history-tick', 'data')],
        prevent_initial_call=True,
    )
    def handle_session_rename(save_clicks, cancel_clicks, session_id, title, language, tick):
        trigger_id = dash.ctx.triggered_id
        if trigger_id == 'chat-session-rename-cancel-btn':
            return None, dash.no_update
        if trigger_id == 'chat-session-rename-save-btn' and save_clicks and session_id:
            rename_session(session_id, title, language or 'en')
            return None, (tick or 0) + 1
        return dash.no_update, dash.no_update

    @app.callback(
        [Output('chat-session-id', 'data', allow_duplicate=True),
         Output('chat-messages', 'children', allow_duplicate=True),
         Output('chat-sessions-open', 'data', allow_duplicate=True),
         Output('chat-scroll-target', 'data'),
         Output('chat-history-tick', 'data', allow_duplicate=True)],
        Input({'type': 'chat-session-button', 'session_id': ALL, 'message_id': ALL}, 'n_clicks'),
        State('chat-language', 'data'),
        State('chat-history-tick', 'data'),
        prevent_initial_call=True,
    )
    def load_chat_session(clicks, language, history_tick):
        triggered = dash.ctx.triggered_id
        click_value = dash.ctx.triggered[0].get('value') if dash.ctx.triggered else 0
        if not isinstance(triggered, dict) or not click_value or not any(clicks or []):
            return (dash.no_update,) * 5

        session_id = triggered.get('session_id')
        target_message_id = triggered.get('message_id') or None
        history = get_history_for_display(session_id, language or 'en')
        return (
            session_id,
            _render_history_messages(history, language or 'en', target_message_id),
            False,
            (
                {'message_id': target_message_id, 'token': str(uuid.uuid4())}
                if target_message_id
                else None
            ),
            (history_tick or 0) + 1,
        )

    @app.callback(
        [Output('chat-session-id', 'data', allow_duplicate=True),
         Output('chat-messages', 'children', allow_duplicate=True),
         Output('chat-history-tick', 'data', allow_duplicate=True),
         Output('chat-rename-session-id', 'data', allow_duplicate=True),
         Output('pending-report', 'data', allow_duplicate=True)],
        Input({'type': 'chat-session-delete-btn', 'session_id': ALL}, 'n_clicks'),
        [State('chat-session-id', 'data'),
         State('chat-language', 'data'),
         State('chat-history-tick', 'data'),
         State('chat-user-id', 'data')],
        prevent_initial_call=True,
    )
    def remove_chat_session(clicks, active_session_id, language, tick, user_id):
        triggered = dash.ctx.triggered_id
        click_value = dash.ctx.triggered[0].get('value') if dash.ctx.triggered else 0
        if not isinstance(triggered, dict) or not click_value:
            return (dash.no_update,) * 5

        session_id = triggered.get('session_id')
        delete_session(session_id, user_id)

        if session_id == active_session_id:
            return (
                str(uuid.uuid4()),
                [_welcome_bubble(language or 'en')],
                (tick or 0) + 1,
                None,
                None,
            )

        return (
            dash.no_update,
            dash.no_update,
            (tick or 0) + 1,
            None,
            dash.no_update,
        )

    @app.callback(
        [Output('chat-language', 'data'),
         Output('language-selection', 'style'),
         Output('chat-interface', 'style'),
         Output('chat-messages', 'children'),
         Output('chat-remember-language', 'value')],
        Input('chat-language-preference', 'modified_timestamp'),
        [State('chat-language-preference', 'data'),
         State('chat-language', 'data')],
    )
    def apply_saved_language(_modified, preference, current_language):
        if current_language or not preference or not preference.get('language'):
            return (dash.no_update,) * 5

        language = preference['language']
        return (
            language,
            {'display': 'none'},
            {'display': 'flex', 'flex': '1', 'flexDirection': 'column', 'minHeight': '0'},
            [_welcome_bubble(language)],
            ['remember'],
        )

    @app.callback(
        [Output('chat-language', 'data', allow_duplicate=True),
         Output('chat-language-preference', 'data'),
         Output('language-selection', 'style', allow_duplicate=True),
         Output('chat-interface', 'style', allow_duplicate=True),
         Output('chat-messages', 'children', allow_duplicate=True),
         Output('chat-history-tick', 'data', allow_duplicate=True)],
        [Input('lang-en-btn', 'n_clicks'),
         Input('lang-es-btn', 'n_clicks')],
        [State('chat-remember-language', 'value'),
         State('chat-history-tick', 'data')],
        prevent_initial_call=True,
    )
    def select_language(en_clicks, es_clicks, remember_value, tick):
        trigger_id = dash.ctx.triggered_id
        if trigger_id not in ('lang-en-btn', 'lang-es-btn'):
            return (dash.no_update,) * 6

        language = 'es' if trigger_id == 'lang-es-btn' else 'en'
        preference = {'language': language} if 'remember' in (remember_value or []) else None

        return (
            language,
            preference,
            {'display': 'none'},
            {'display': 'flex', 'flex': '1', 'flexDirection': 'column', 'minHeight': '0'},
            [_welcome_bubble(language)],
            (tick or 0) + 1,
        )

    @app.callback(
        [Output('chat-language', 'data', allow_duplicate=True),
         Output('chat-language-preference', 'data', allow_duplicate=True),
         Output('chat-messages', 'children', allow_duplicate=True),
         Output('chat-history-tick', 'data', allow_duplicate=True)],
        [Input('chat-language-toggle-btn', 'n_clicks'),
         Input('pending-language-switch', 'data')],
        [State('chat-language', 'data'),
         State('chat-language-preference', 'data'),
         State('chat-session-id', 'data'),
         State('chat-history-tick', 'data')],
        prevent_initial_call=True,
    )
    def switch_language(toggle_clicks, pending_switch, current_language, preference, session_id, tick):
        trigger_id = dash.ctx.triggered_id
        current_language = current_language or 'en'

        if trigger_id == 'chat-language-toggle-btn':
            if not toggle_clicks:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
            new_language = 'en' if current_language == 'es' else 'es'
        elif trigger_id == 'pending-language-switch':
            # Slash command (/spanish, /english). Payload is the target language.
            if not pending_switch:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
            new_language = 'es' if pending_switch == 'es' else 'en'
            if new_language == current_language:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        else:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        # Persist the new choice only if the user opted to be remembered.
        preference_update = dash.no_update
        if preference and preference.get('language'):
            preference_update = {'language': new_language}

        if not session_id or not mongo_available():
            messages = [_welcome_bubble(new_language)]
        else:
            history = get_history_for_display(session_id, new_language)
            messages = (
                _render_history_messages(history, new_language)
                if history
                else [_welcome_bubble(new_language)]
            )

        return new_language, preference_update, messages, (tick or 0) + 1

    @app.callback(
        Output('chat-messages', 'children', allow_duplicate=True),
        Input('chat-language', 'data'),
        [State('chat-session-id', 'data'),
         State('chat-messages', 'children')],
        prevent_initial_call=True,
    )
    def retranslate_visible_conversation(language, session_id, messages):
        # Re-render the whole visible thread in the newly selected language so
        # nothing stays in the old language. Reuses the same DB-backed load path
        # as load_chat_session; falls back to a welcome bubble for empty threads.
        if not language or not session_id or not mongo_available():
            return dash.no_update
        history = get_history_for_display(session_id, language)
        if not history:
            # No persisted turns yet (e.g. right after the entry choice). Leave
            # the current bubbles as-is rather than wiping them.
            return dash.no_update
        return _render_history_messages(history, language)

    @app.callback(
        [Output('chat-session-id', 'data', allow_duplicate=True),
         Output('chat-messages', 'children', allow_duplicate=True),
         Output('chat-sessions-open', 'data', allow_duplicate=True),
         Output('pending-report', 'data', allow_duplicate=True),
         Output('chat-history-tick', 'data', allow_duplicate=True)],
        # "Reset dashboard" also starts a clean conversation, so answers never
        # lean on context from before the reset (usability study [E3-R4]).
        [Input('chat-new-session-btn', 'n_clicks'),
         Input('reset-btn', 'n_clicks')],
        [State('chat-language', 'data'),
         State('chat-history-tick', 'data')],
        prevent_initial_call=True,
    )
    def start_new_chat_session(n_clicks, reset_clicks, language, tick):
        if not (n_clicks or reset_clicks):
            return (dash.no_update,) * 5
        return (
            str(uuid.uuid4()),
            [_welcome_bubble(language or 'en')],
            False,
            None,
            (tick or 0) + 1,
        )

    @app.callback(
        [Output('chat-messages', 'children', allow_duplicate=True),
         Output('chat-input', 'value'),
         Output('pending-user-message', 'data'),
         Output('chat-session-id', 'data'),
         Output('chat-history-tick', 'data', allow_duplicate=True),
         Output('pending-language-switch', 'data'),
         Output('pending-delete-confirm', 'data'),
         Output('chat-send-btn', 'children', allow_duplicate=True),
         Output('chat-generating', 'data', allow_duplicate=True),
         Output('chat-cancelled', 'data', allow_duplicate=True)],
        [Input('chat-send-btn', 'n_clicks'),
         Input('chat-input', 'n_submit')],
        [State('chat-input', 'value'),
         State('chat-messages', 'children'),
         State('chat-language', 'data'),
         State('chat-session-id', 'data'),
         State('chat-user-id', 'data'),
         State('chat-history-tick', 'data'),
         State('pending-delete-confirm', 'data'),
         State('chat-generating', 'data')],
        prevent_initial_call=True,
    )
    def show_user_message(
        n_clicks, n_submit, user_input, messages, language, session_id, user_id,
        history_tick, delete_pending, generating
    ):
        trigger_id = dash.ctx.triggered_id

        # Stop button: the send button clicked while a reply is generating acts
        # as a Stop — cancel the in-flight reply, drop the typing indicator, and
        # restore the arrow. (The input keeps whatever the user is typing.)
        if trigger_id == 'chat-send-btn' and generating:
            messages = [m for m in (messages or []) if not _is_typing_indicator(m)]
            return (
                messages,
                dash.no_update,
                None,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                '➤',
                None,
                generating,  # mark this nonce cancelled so its result is dropped
            )

        if not (n_clicks or n_submit) or not user_input or not user_input.strip():
            return (dash.no_update,) * 10

        language = language or 'en'
        command = user_input.strip().lower()

        # Any command other than a fresh /delete clears a pending confirmation,
        # so a stale "yes" can never delete after an unrelated message.
        clear_confirm = False if delete_pending else dash.no_update

        # Trailing three values are (chat-send-btn.children, chat-generating,
        # chat-cancelled). Commands don't start a reply, so the send button keeps
        # its arrow and no generation is started.
        def _bubble_reply(message):
            """Append an assistant bubble, clear input, no other side effects."""
            return (
                [
                    *(messages or []),
                    _ai_bubble(
                        message,
                        timestamp=datetime.utcnow().isoformat(),
                        language=language,
                    ),
                ],
                '',
                None,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                clear_confirm,
                '➤',
                None,
                dash.no_update,
            )

        # Commands that read or change saved history need the chat database.
        if (command == '/delete' or command.startswith('/name')) and not mongo_available():
            return _bubble_reply(
                'El historial de chats no está disponible temporalmente.'
                if language == 'es' else
                'Chat history is temporarily unavailable, so that command cannot run right now.'
            )

        if command in {'/new', '/session'}:
            return (
                [_welcome_bubble(language)],
                '',
                None,
                str(uuid.uuid4()),
                (history_tick or 0) + 1,
                dash.no_update,
                clear_confirm,
                '➤',
                None,
                dash.no_update,
            )

        # ── Language switch commands ────────────────────────────────────────
        if command in {'/spanish', '/español', '/es'}:
            reply = 'Idioma cambiado a Español.' if language != 'es' else 'Ya estás en Español.'
            base = _bubble_reply(reply)
            return (*base[:5], 'es', clear_confirm, '➤', None, dash.no_update)
        if command in {'/english', '/en'}:
            reply = 'Language switched to English.' if language != 'en' else 'Already in English.'
            base = _bubble_reply(reply)
            return (*base[:5], 'en', clear_confirm, '➤', None, dash.no_update)

        # ── Delete all history (ask for confirmation first) ─────────────────
        if command == '/delete':
            if delete_pending:
                # Second /delete confirms — wipe everything and start fresh.
                delete_all_user_data(user_id)
                reply = (
                    'Se eliminó todo el historial de chat y los resúmenes.'
                    if language == 'es'
                    else 'All chat history and summaries have been deleted.'
                )
                return (
                    [_welcome_bubble(language),
                     _ai_bubble(reply, timestamp=datetime.utcnow().isoformat(), language=language)],
                    '',
                    None,
                    str(uuid.uuid4()),
                    (history_tick or 0) + 1,
                    dash.no_update,
                    False,
                    '➤',
                    None,
                    dash.no_update,
                )
            prompt = (
                '¿Estás seguro de que deseas eliminar todo el historial de chat y '
                'todos los resúmenes de sesión de todas las sesiones? '
                'Escribe /delete otra vez para confirmar, o /cancel para cancelar.'
                if language == 'es'
                else 'Are you sure you want to delete the entire chat history and all '
                'session summaries across all sessions? Type /delete again to '
                'confirm, or /cancel to cancel.'
            )
            base = _bubble_reply(prompt)
            return (*base[:6], True, '➤', None, dash.no_update)
        if command == '/cancel':
            reply = 'Cancelado.' if language == 'es' else 'Cancelled.'
            base = _bubble_reply(reply)
            return (*base[:6], False, '➤', None, dash.no_update)

        if command == '/name' or command.startswith('/name '):
            name = user_input.strip()[len('/name'):].strip()
            if not name:
                message = (
                    'Escribe /name seguido de tu nombre, por ejemplo: /name Tom'
                    if language == 'es'
                    else 'Use /name followed by your name, for example: /name Tom'
                )
            elif not user_id:
                message = (
                    'Tu ID de dispositivo aún se está cargando. Intenta /name de nuevo.'
                    if language == 'es'
                    else 'Your device ID is still loading. Please try /name again.'
                )
            elif not all(char.isalpha() or char in " .'-" for char in name):
                message = (
                    'Los nombres pueden contener letras, espacios, apóstrofes, puntos y guiones.'
                    if language == 'es'
                    else 'Names may contain letters, spaces, apostrophes, periods, and hyphens.'
                )
            else:
                name = ' '.join(name.split())[:80]
                set_user_name(user_id, name)
                message = (
                    f'Got it, {name}. I will remember your name on this device.'
                    if language != 'es'
                    else f'Entendido, {name}. Recordaré tu nombre en este dispositivo.'
                )
            return _bubble_reply(message)

        # Name-on-first-chat, step 1: the first time a logged-in user sends a
        # message and we have no name yet, ASK for their name (we don't treat this
        # first message as the name — they might open with "hi"). Mark that we've
        # asked so we only prompt once.
        db_up = bool(user_id) and mongo_available()
        if db_up and not command.startswith('/') and not get_name_prompted(user_id):
            set_name_prompted(user_id)
            ask = (
                '¡Hola! Antes de empezar, ¿cómo te gustaría que te llame?'
                if language == 'es'
                else 'Hi! Before we start, what should I call you?'
            )
            return (
                [
                    *(messages or []),
                    _user_bubble(user_input, timestamp=datetime.utcnow().isoformat(),
                                 language=language),
                    _ai_bubble(ask, timestamp=datetime.utcnow().isoformat(),
                               language=language),
                ],
                '', None, dash.no_update, dash.no_update, dash.no_update,
                clear_confirm, '➤', None, dash.no_update,
            )

        # Name-on-first-chat, step 2: we asked last turn (name_prompted is set) but
        # still have no name. If this message looks like a name, store it and greet.
        if db_up and not command.startswith('/') and not get_user_name(user_id):
            candidate = ' '.join(user_input.strip().split())
            looks_like_name = (
                0 < len(candidate) <= 40
                and all(ch.isalpha() or ch in " .'-" for ch in candidate)
            )
            if looks_like_name:
                name = candidate[:80]
                set_user_name(user_id, name)
                greeting = (
                    f'¡Encantado, {name}! ¿En qué te puedo ayudar sobre el panel?'
                    if language == 'es'
                    else f'Nice to meet you, {name}! How can I help you with the dashboard?'
                )
                return (
                    [
                        *(messages or []),
                        _user_bubble(user_input, timestamp=datetime.utcnow().isoformat(),
                                     language=language),
                        _ai_bubble(greeting, timestamp=datetime.utcnow().isoformat(),
                                   language=language),
                    ],
                    '', None, dash.no_update, dash.no_update, dash.no_update,
                    clear_confirm, '➤', None, dash.no_update,
                )
            # Not a name (they asked a real question instead) — fall through and
            # answer it normally; get_user_name stays empty, no more prompting.

        messages = list(messages or [])
        messages.append(
            _user_bubble(
                user_input,
                timestamp=datetime.utcnow().isoformat(),
                language=language,
            )
        )
        messages.append(_typing_bubble())

        nonce = uuid.uuid4().hex
        return (
            messages,
            '',
            {'text': user_input, 'n': n_clicks, 'nonce': nonce},
            dash.no_update,
            dash.no_update,
            dash.no_update,
            clear_confirm,
            # While generating, the send button becomes a Stop control (theme
            # color kept via CSS). Input stays enabled so the user can keep
            # typing; clicking Stop cancels this reply (via the nonce).
            '■',
            nonce,
            dash.no_update,
        )

    @app.callback(
        [Output('chat-messages', 'children', allow_duplicate=True),
         Output('chat-history-tick', 'data', allow_duplicate=True),
         Output('pending-report', 'data', allow_duplicate=True),
         Output('chat-send-btn', 'children', allow_duplicate=True),
         Output('chat-generating', 'data', allow_duplicate=True),
         Output('download-pdf', 'data', allow_duplicate=True),
         Output('chat-download-state', 'data', allow_duplicate=True)],
        Input('pending-user-message', 'data'),
        [State('chat-messages', 'children'),
         State('chat-language', 'data'),
         State('chat-session-id', 'data'),
         State('chat-user-id', 'data'),
         State('chat-history-tick', 'data'),
         State('chat-cancelled', 'data'),
         # What the dashboard is showing (municipalities, indicators, year,
         # display mode), so "what is this value?" is answered from it.
         State('dashboard-state', 'data')],
        prevent_initial_call=True,
    )
    def generate_ai_response(
        pending, messages, language, session_id, user_id, tick, cancelled,
        dashboard_state=None,
    ):
        nu = dash.no_update
        if not pending or not pending.get('text'):
            return nu, nu, nu, '➤', None, nu, nu

        print(
            f"[generate_ai_response] text={pending.get('text')!r} "
            f"session_id={session_id!r} user_id={user_id!r} language={language!r}"
        )

        nonce = pending.get('nonce')
        try:
            ai_response = process_chat_message(
                pending['text'], language or 'en', session_id, user_id,
                dashboard_state=dashboard_state,
            )
        except Exception as e:
            print(f"[generate_ai_response] error: {e}")
            ai_response = {
                "kind": "text",
                "text": "The AI assistant is currently unavailable.",
            }

        # If the user pressed Stop while this reply was generating, discard it.
        # (The response is already saved in chat.db, but we don't render a bubble
        # and we don't bump the tick — the Stop handler already removed the
        # typing indicator and restored the arrow.)
        if nonce and cancelled == nonce:
            print("[generate_ai_response] cancelled by user, dropping reply")
            return nu, nu, nu, nu, None, nu, nu

        messages = [m for m in (messages or []) if not _is_typing_indicator(m)]

        pending_report_update = dash.no_update
        download_update = chat_download_state = dash.no_update
        assistant_timestamp = datetime.utcnow().isoformat()
        kind = ai_response.get('kind') if isinstance(ai_response, dict) else None
        if kind == 'grounded':
            # Answered from the dashboard's own data: shows the rows it used and
            # offers "View these values in the graph" (dashboard/chat_bridge.py).
            messages.append(grounded_bubble(ai_response, language or 'en'))
        elif kind == 'export_chat':
            # "Export this conversation" — download the transcript, as the
            # ⋮ menu's Download Chat PDF does, instead of building a report.
            messages.append(_ai_bubble(ai_response.get('text', ''),
                                       timestamp=assistant_timestamp,
                                       language=language or 'en'))
            history = (get_history_for_display(session_id, language or 'en')
                       if session_id and mongo_available() else [])
            if history:
                pdf_bytes = build_pdf_bytes(history, language=language or 'en')
                stamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
                download_update = dcc.send_bytes(
                    lambda f: f.write(pdf_bytes),
                    filename=f'chat_transcript_{stamp}.pdf')
                chat_download_state = {
                    'downloaded': True, 'ts': stamp,
                    'label': '¡Descargado!' if language == 'es' else 'Downloaded!'}
        elif kind == 'report':
            messages.append(
                _report_bubble(
                    ai_response.get('message', ''),
                    language or 'en',
                    timestamp=assistant_timestamp,
                )
            )
            pending_report_update = {
                'token': ai_response.get('report_token'),
                'filename': ai_response.get('filename'),
            }
        else:
            text = (
                ai_response.get('text')
                if isinstance(ai_response, dict)
                else str(ai_response)
            )
            messages.append(
                _ai_bubble(
                    text or '',
                    timestamp=assistant_timestamp,
                    language=language or 'en',
                )
            )

        # Reply is ready — restore the arrow and clear the generating flag.
        return (messages, (tick or 0) + 1, pending_report_update, '➤', None,
                download_update, chat_download_state)

    # Chat PDF always re-downloads on click; success is shown via the
    # blurred "Downloaded!" overlay (see clientside_callback above), not a
    # re-download confirmation.
    @app.callback(
        [Output('download-pdf', 'data'), Output('chat-download-state', 'data')],
        Input('download-pdf-btn', 'n_clicks'),
        [State('chat-session-id', 'data'), State('chat-language', 'data')],
        prevent_initial_call=True,
    )
    def export_chat_pdf(n_clicks, session_id, language):
        if not n_clicks or not session_id or not mongo_available():
            return dash.no_update, dash.no_update

        history = get_history_for_display(session_id, language or 'en')
        if not history:
            return dash.no_update, dash.no_update

        pdf_bytes = build_pdf_bytes(history, language=language or 'en')
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        filename = f'chat_transcript_{timestamp}.pdf'

        overlay_label = '¡Descargado!' if language == 'es' else 'Downloaded!'
        new_state = {'downloaded': True, 'ts': timestamp, 'label': overlay_label}
        return dcc.send_bytes(lambda f: f.write(pdf_bytes), filename=filename), new_state

    # Report PDF: first click downloads and flips the button to "Downloaded"
    # (see update_report_download_button below). Clicking again asks for
    # confirmation via download-confirm-modal before re-downloading.
    @app.callback(
        [
            Output('download-report', 'data', allow_duplicate=True),
            Output('report-download-state', 'data', allow_duplicate=True),
            Output('download-confirm-modal', 'style', allow_duplicate=True),
        ],
        Input('download-report-btn', 'n_clicks'),
        [State('pending-report', 'data'), State('report-download-state', 'data')],
        prevent_initial_call=True,
    )
    def export_report_pdf(n_clicks, pending, report_state):
        if not n_clicks or not pending or not pending.get('token'):
            return dash.no_update, dash.no_update, dash.no_update

        token = pending['token']
        # report-download-state is keyed by token so a *new* report always
        # starts as "not yet downloaded", even if a previous report was.
        state_for_token = report_state if (report_state and report_state.get('token') == token) else {}

        # download-report-btn lives inside chat-messages.children, which several
        # other callbacks wholesale-replace on every chat turn (typing indicator,
        # then the reply). Dash re-fires this Input with the button's *current*
        # n_clicks each time that happens, even though nothing was actually
        # clicked — so only react once per genuinely new n_clicks value.
        handled_clicks = state_for_token.get('clicks_handled', 0)
        if n_clicks <= handled_clicks:
            return dash.no_update, dash.no_update, dash.no_update

        if state_for_token.get('downloaded'):
            new_state = dict(state_for_token, clicks_handled=n_clicks)
            return dash.no_update, new_state, {'display': 'block'}

        result = consume_report(token)
        if result is None:
            new_state = dict(state_for_token, clicks_handled=n_clicks)
            return dash.no_update, new_state, dash.no_update
        pdf_bytes, filename = result
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        new_state = {'downloaded': True, 'token': token, 'clicks_handled': n_clicks, 'ts': timestamp}
        return dcc.send_bytes(lambda f: f.write(pdf_bytes), filename=filename), new_state, dash.no_update

    @app.callback(
        Output('download-pdf-btn', 'disabled'),
        Input('chat-history-tick', 'data'),
        State('chat-session-id', 'data'),
    )
    def toggle_pdf_button(_tick, session_id):
        if not session_id or not mongo_available():
            return True
        history = get_history_for_display(session_id)
        if not history:
            return True
        return not any(m.get('role') == 'assistant' for m in history)

    @app.callback(
        [Output('download-report-btn', 'children'), Output('download-report-btn', 'className')],
        [Input('report-download-state', 'data'), Input('chat-language', 'data'), Input('pending-report', 'data')],
        prevent_initial_call='initial_duplicate',
    )
    def update_report_download_button(report_state, language, pending):
        # download-report-btn only exists in the DOM once a report bubble has
        # been rendered in the current session; updating it while absent
        # throws a "nonexistent object" error in dash-renderer.
        if not (pending and pending.get('token')):
            return dash.no_update, dash.no_update

        downloaded = bool(
            (report_state or {}).get('downloaded')
            and (report_state or {}).get('token') == pending.get('token')
        )
        if language == 'es':
            label = '¡Descargado!' if downloaded else 'Descargar informe'
        else:
            label = 'Downloaded!' if downloaded else 'Download report'
        return label, ('downloaded-btn' if downloaded else '')

    # Confirm modal handlers (report re-downloads only): Yes -> download again; No -> hide modal
    @app.callback(
        [Output('download-report', 'data', allow_duplicate=True),
         Output('download-confirm-modal', 'style', allow_duplicate=True),
         Output('report-download-state', 'data', allow_duplicate=True)],
        [Input('download-confirm-yes', 'n_clicks'), Input('download-confirm-no', 'n_clicks')],
        [State('pending-report', 'data'), State('report-download-state', 'data')],
        prevent_initial_call=True,
    )
    def handle_download_confirm(yes_clicks, no_clicks, pending, report_state):
        trigger = dash.ctx.triggered_id
        if trigger == 'download-confirm-no':
            return dash.no_update, {'display': 'none'}, dash.no_update

        if not pending or not pending.get('token'):
            return dash.no_update, {'display': 'none'}, dash.no_update

        result = consume_report(pending['token'])
        if result is None:
            return dash.no_update, {'display': 'none'}, dash.no_update
        pdf_bytes, filename = result
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        # Preserve clicks_handled from report-download-state so the replay
        # guard in export_report_pdf stays consistent after this re-download.
        new_report_state = dict(report_state or {}, downloaded=True, token=pending['token'], ts=timestamp)
        return dcc.send_bytes(lambda f: f.write(pdf_bytes), filename=filename), {'display': 'none'}, new_report_state

    @app.callback(
        [Output('chat-header-label', 'children'),
         Output('chat-fit-window-btn', 'children'),
         Output('download-pdf-btn', 'children'),
         Output('chat-btn', 'children'),
         Output('chat-sessions-btn', 'children'),
         Output('chat-new-session-btn', 'children'),
         Output('chat-panel-title', 'children'),
         Output('chat-session-search', 'placeholder'),
         Output('chat-session-rename-input', 'placeholder'),
         Output('chat-remember-language-label', 'children'),
         Output('chat-input', 'placeholder'),
         Output('chat-language-toggle-btn', 'children')],
        [Input('chat-language', 'data'),
         Input('chat-sessions-open', 'data'),
         Input('chat-window-state', 'data')],
    )
    def translate_chat_header(language, sessions_open, window_state):
        fit_label = '🗕 Minimizar' if (window_state or {}).get('fit') else '⛶ Ajustar ventana'
        if language == 'es':
            return (
                'Asistente de IA',
                fit_label,
                '⬇ Descargar Chat PDF',
                'Asistente de IA',
                '🗂️ ' + ('Ocultar historial' if sessions_open else 'Historial de chats'),
                '＋ Nuevo chat',
                'Tus chats',
                'Buscar conversaciones...',
                'Renombrar conversación...',
                'Recordarme en este navegador',
                'Escribe tu pregunta...',
                # Label shows the *other* language you can switch to.
                '🌐 English',
            )
        fit_label = '🗕 Minimize' if (window_state or {}).get('fit') else '⛶ Fit Window'
        return (
            'AI Assistant',
            fit_label,
            '⬇ Download Chat PDF',
            'AI Assistant',
            '🗂️ ' + ('Hide Chat History' if sessions_open else 'Chat History'),
            '＋ New Chat',
            'Your chats',
            'Search conversations...',
            'Rename conversation...',
            'Remember me on this browser',
            'Ask something...',
            '🌐 Español',
        )

    # ----- Ticket modal -----
    @app.callback(
        [Output('ticket-modal', 'style'),
         Output('ticket-msg', 'children', allow_duplicate=True),
         Output('ticket-category', 'value', allow_duplicate=True),
         Output('ticket-subject', 'value', allow_duplicate=True),
         Output('ticket-message', 'value', allow_duplicate=True)],
        [Input('open-ticket-btn', 'n_clicks'),
         Input('ticket-modal-close', 'n_clicks')],
        prevent_initial_call=True,
    )
    def toggle_ticket_modal(open_clicks, close_clicks):
        trigger = dash.ctx.triggered_id
        if trigger == 'open-ticket-btn':
            return {'display': 'block'}, '', None, '', ''
        return {'display': 'none'}, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    @app.callback(
        [Output('ticket-msg', 'children'),
         Output('ticket-category', 'value'),
         Output('ticket-subject', 'value'),
         Output('ticket-message', 'value')],
        Input('ticket-submit-btn', 'n_clicks'),
        [State('chat-user-id', 'data'),
         State('ticket-category', 'value'),
         State('ticket-subject', 'value'),
         State('ticket-message', 'value')],
        prevent_initial_call=True,
    )
    def submit_ticket(n_clicks, user_id, category, subject, message):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        if not user_id:
            return 'Please log in again.', dash.no_update, dash.no_update, dash.no_update
        if not mongo_available():
            return ('Reporting an issue is ' + _UNAVAILABLE['en'] +
                    '. Please try again later.'), dash.no_update, dash.no_update, dash.no_update
        from tickets.core import create_ticket
        user = get_public_user(user_id)
        email = user['email'] if user else ''
        _, err = create_ticket(user_id, email, category, subject, message)
        if err:
            return err, dash.no_update, dash.no_update, dash.no_update
        return '✅ Ticket submitted — thank you!', None, '', ''
