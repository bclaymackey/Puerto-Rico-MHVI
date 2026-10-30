import uuid

from dash import dcc, html

from auth.policy import login_required
from tickets.core import CATEGORIES as _TICKET_CATEGORIES


def build_layout(dashboard_children) -> html.Div:
    """The whole page.

    dashboard_children: a function returning the dashboard's components (the
    map, panel, tables and dialogs — see dashboard/layout.py). It is given the
    account button to place in the dashboard's header.

    Whether the sign-in page comes first is set by REQUIRE_LOGIN (auth/policy.py).
    """
    required = login_required()
    return html.Div([
        # Resolves the auth cookie on load; drives the login gate below.
        dcc.Store(id='chat-user-id'),
        # True while a visitor has asked to sign in (only used when signing in
        # is optional — the "Sign in" button opens the login page).
        dcc.Store(id='login-requested', data=False),
        _build_login_page(show=required),
        # With REQUIRE_LOGIN on, the app is hidden until authenticated; the
        # gate reveals it. With it off, the app is visible from the start.
        html.Div(
            id='app-body',
            style={'display': 'none' if required else 'block'},
            children=[
                *dashboard_children(header_extras=[_account_menu()]),
                _ticket_modal(),
                *_chat_widget(),
            ],
        ),
        # confirmation modal for repeated report downloads
        html.Div(
            id='download-confirm-modal',
            style={'display': 'none'},
            children=[
                html.Div(
                    style={'position': 'fixed', 'top': '0', 'left': '0', 'width': '100vw', 'height': '100vh',
                           'backgroundColor': 'rgba(0,0,0,0.4)', 'zIndex': '4000'},
                    children=[
                        html.Div(
                            style={'position': 'absolute', 'top': '50%', 'left': '50%',
                                   'transform': 'translate(-50%, -50%)', 'backgroundColor': 'white',
                                   'padding': '20px', 'borderRadius': '8px', 'width': 'min(90vw, 420px)',
                                   'boxShadow': '0 8px 30px rgba(0,0,0,0.2)'},
                            children=[
                                html.Div('Download report again?', style={'fontWeight': '700', 'marginBottom': '12px'}),
                                html.Div('Are you sure you would like to download this report again?', style={'marginBottom': '16px'}),
                                html.Div([
                                    html.Button('Yes', id='download-confirm-yes', n_clicks=0,
                                                style={'marginRight': '8px', 'padding': '8px 12px', 'background': '#4b0082', 'color': 'white', 'border': 'none', 'borderRadius': '6px'}),
                                    html.Button('No', id='download-confirm-no', n_clicks=0,
                                                style={'padding': '8px 12px', 'background': '#eee', 'border': 'none', 'borderRadius': '6px'}),
                                ], style={'display': 'flex', 'justifyContent': 'flex-end'})
                            ]
                        )
                    ]
                )
            ]
        ),
    ], style={'fontFamily': 'Arial'})


_ACCOUNT_INPUT = {
    'width': '100%', 'padding': '8px 10px', 'marginBottom': '8px',
    'borderRadius': '8px', 'border': '1px solid #d7c9ea',
    'fontSize': '12px', 'boxSizing': 'border-box',
}
_ACCOUNT_ACTION_BTN = {
    'width': '100%', 'padding': '8px', 'borderRadius': '8px', 'border': 'none',
    'background': '#4b0082', 'color': 'white', 'fontSize': '12px',
    'fontWeight': '600', 'cursor': 'pointer',
}

_ACCOUNT_DISCLOSURE = {
    'borderTop': '1px solid #eee7f5',
    'padding': '2px 0',
}
_ACCOUNT_SUMMARY = {
    'padding': '12px 2px', 'fontWeight': '700', 'fontSize': '12px',
    'color': '#31104f', 'cursor': 'pointer', 'listStylePosition': 'inside',
}


def _account_menu() -> html.Div:
    """Settings menu with collapsible account actions and sign-out, placed at
    the right-hand end of the dashboard header (next to the logos).

    When nobody is signed in the button reads "Sign in" and opens the login
    page instead (see callbacks.py: account_button_label / request_login)."""
    return html.Div(
        style={'position': 'relative', 'marginLeft': '16px', 'zIndex': '900'},
        children=[
            html.Div(
                html.Button(
                    # Relabelled by account_button_label once the visitor is
                    # known; start with the likelier label to avoid a flicker.
                    '⚙ Settings' if login_required() else '👤 Sign in',
                    id='account-menu-btn',
                    n_clicks=0,
                    **{'aria-label': 'Open account settings'},
                    style={
                        'padding': '7px 14px', 'borderRadius': '10px',
                        'border': '1px solid #d7c9ea', 'background': 'white',
                        'color': '#4b0082', 'fontSize': '12px', 'fontWeight': '600',
                        'cursor': 'pointer', 'boxShadow': '0 2px 8px rgba(75,0,130,0.12)',
                    },
                ),
                style={'display': 'flex', 'justifyContent': 'flex-end'},
            ),
            html.Div(
                id='account-panel',
                style={
                    'display': 'none',  # toggled by the account-menu callback
                    'position': 'absolute', 'top': '44px', 'right': '0',
                    'width': '280px', 'padding': '16px',
                    'background': 'white', 'borderRadius': '14px',
                    'boxShadow': '0 16px 40px rgba(75, 0, 130, 0.20)',
                    'border': '1px solid #eee',
                },
                children=[
                    html.Div('Account', style={'fontWeight': '700', 'fontSize': '14px',
                                               'color': '#31104f'}),
                    html.Div(id='account-email',
                             style={'fontSize': '12px', 'color': '#7a5aa6',
                                    'margin': '2px 0 12px', 'wordBreak': 'break-all'}),

                    html.Details(
                        style=_ACCOUNT_DISCLOSURE,
                        children=[
                            html.Summary('Change password', style=_ACCOUNT_SUMMARY),
                            html.Div([
                                dcc.Input(id='account-current-pw', type='password',
                                          placeholder='Current password', style=_ACCOUNT_INPUT),
                                dcc.Input(id='account-new-pw', type='password',
                                          placeholder='New password', style=_ACCOUNT_INPUT),
                                html.Button('Update password', id='account-change-pw-btn',
                                            n_clicks=0, style=_ACCOUNT_ACTION_BTN),
                                html.Div(id='account-pw-msg',
                                         style={'fontSize': '11px', 'minHeight': '14px',
                                                'marginTop': '6px', 'color': '#7a5aa6'}),
                            ], style={'padding': '0 2px 8px'}),
                        ],
                    ),
                    html.Details(
                        style=_ACCOUNT_DISCLOSURE,
                        children=[
                            html.Summary('Security question', style=_ACCOUNT_SUMMARY),
                            html.Div([
                                dcc.Input(id='account-secq', type='text',
                                          placeholder='Question (e.g. First pet’s name?)',
                                          style=_ACCOUNT_INPUT),
                                dcc.Input(id='account-seca', type='text',
                                          placeholder='Answer', style=_ACCOUNT_INPUT),
                                html.Button('Save security question', id='account-secq-btn',
                                            n_clicks=0, style=_ACCOUNT_ACTION_BTN),
                                html.Div(id='account-secq-msg',
                                         style={'fontSize': '11px', 'minHeight': '14px',
                                                'marginTop': '6px', 'color': '#7a5aa6'}),
                            ], style={'padding': '0 2px 8px'}),
                        ],
                    ),
                    html.Button(
                        '🛟 Report an issue',
                        id='open-ticket-btn',
                        n_clicks=0,
                        style={
                            'width': '100%', 'padding': '11px 2px',
                            'marginTop': '2px', 'border': 'none',
                            'borderTop': '1px solid #eee7f5', 'background': 'transparent',
                            'color': '#4b0082', 'fontSize': '12px', 'fontWeight': '700',
                            'textAlign': 'left', 'cursor': 'pointer',
                        },
                    ),
                    html.Button(
                        'Sign out', id='sign-out-btn', n_clicks=0,
                        style={
                            'width': '100%', 'padding': '11px 2px',
                            'marginTop': '2px', 'border': 'none',
                            'borderTop': '1px solid #eee7f5', 'background': 'transparent',
                            'color': '#4b0082', 'fontSize': '12px', 'fontWeight': '700',
                            'textAlign': 'left', 'cursor': 'pointer',
                        },
                    ),
                ],
            ),
        ],
    )







def _ticket_modal() -> html.Div:
    """Overlay modal for submitting a support ticket. Hidden until opened."""
    cat_options = [{'label': c, 'value': c} for c in _TICKET_CATEGORIES]
    return html.Div(
        id='ticket-modal',
        style={'display': 'none'},
        children=[
            html.Div(
                style={
                    'position': 'fixed', 'top': '0', 'left': '0',
                    'width': '100vw', 'height': '100vh',
                    'backgroundColor': 'rgba(0,0,0,0.4)', 'zIndex': '2000',
                },
                children=[
                    html.Div(
                        style={
                            'position': 'absolute', 'top': '50%', 'left': '50%',
                            'transform': 'translate(-50%, -50%)',
                            'width': 'min(90vw, 480px)',
                            'backgroundColor': 'white', 'borderRadius': '10px',
                            'padding': '24px',
                            'boxShadow': '0 8px 30px rgba(0,0,0,0.2)',
                        },
                        children=[
                            html.Div([
                                html.Div('Report an issue',
                                         style={'fontWeight': '700', 'fontSize': '16px',
                                                'color': '#31104f'}),
                                html.Button('✖', id='ticket-modal-close', n_clicks=0,
                                            style={'border': 'none', 'background': 'transparent',
                                                   'fontSize': '18px', 'cursor': 'pointer'}),
                            ], style={'display': 'flex', 'justifyContent': 'space-between',
                                      'alignItems': 'center', 'marginBottom': '16px'}),
                            dcc.Dropdown(
                                id='ticket-category',
                                options=cat_options,
                                placeholder='Category',
                                clearable=False,
                                style={'marginBottom': '10px', 'fontSize': '13px'},
                            ),
                            dcc.Input(
                                id='ticket-subject',
                                type='text',
                                placeholder='Subject',
                                maxLength=120,
                                style=_AUTH_INPUT_STYLE,
                            ),
                            dcc.Textarea(
                                id='ticket-message',
                                placeholder='Describe the issue…',
                                maxLength=2000,
                                style={**_AUTH_INPUT_STYLE,
                                       'height': '120px', 'resize': 'vertical'},
                            ),
                            html.Button(
                                'Submit',
                                id='ticket-submit-btn',
                                n_clicks=0,
                                style=_AUTH_BTN_STYLE,
                            ),
                            html.Div(id='ticket-msg',
                                     style={'fontSize': '12px', 'minHeight': '16px',
                                            'marginTop': '8px', 'color': '#7a5aa6'}),
                        ],
                    ),
                ],
            ),
        ],
    )



_CHAT_MENU_ITEM_STYLE = {
    'fontSize': '13px',
    'padding': '10px 14px',
    'border': 'none',
    'borderRadius': '0',
    'background': 'white',
    'color': '#4b0082',
    'textAlign': 'left',
    'cursor': 'pointer',
    'whiteSpace': 'nowrap',
}

_CHAT_WINDOW_DEFAULT_WIDTH = 300
_CHAT_WINDOW_DEFAULT_HEIGHT = 400

_CHAT_RESIZE_HANDLE_STYLE = {
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


def _chat_widget() -> list:
    """Returns [chat_button, chat_popup] — both are children of the main-content flex row."""
    chat_btn = html.Button(
        'AI Assistant',
        id='chat-btn',
        style={
            'position': 'fixed', 'bottom': '20px', 'left': '20px', 'zIndex': '1000',
            'padding': '12px 16px', 'borderRadius': '8px', 'border': 'none',
            'background': 'linear-gradient(135deg, #03123e 0%, #4b0082 100%)',
            'color': 'white', 'cursor': 'pointer'
        }
    )

    chat_popup = html.Div(
        id='chat-popup',
        style={
            'display': 'none',
            'position': 'fixed',
            'bottom': '80px', 'left': '20px',
            'width': f'{_CHAT_WINDOW_DEFAULT_WIDTH}px',
            'height': f'{_CHAT_WINDOW_DEFAULT_HEIGHT}px',
            'minWidth': '280px', 'minHeight': '350px',
            'maxWidth': '90vw', 'maxHeight': '85vh',
            'backgroundColor': 'white', 'border': '1px solid #ccc',
            'borderRadius': '10px', 'boxShadow': '0 4px 10px rgba(0,0,0,0.2)',
            'zIndex': '1000', 'padding': '10px',
            'flexDirection': 'column',
            'boxSizing': 'border-box'
        },
        children=[
            dcc.Store(id='chat-window-state', data={'open': False, 'fit': False}),
            dcc.Store(
                id='chat-window-size',
                data={'width': _CHAT_WINDOW_DEFAULT_WIDTH, 'height': _CHAT_WINDOW_DEFAULT_HEIGHT},
            ),
            html.Div(
                id='chat-resize-handle',
                style=_CHAT_RESIZE_HANDLE_STYLE,
            ),
            dcc.Store(id='pending-user-message'),
            dcc.Store(id='chat-language', data=None),
            dcc.Store(id='chat-language-preference', storage_type='local'),
            dcc.Store(id='pending-language-switch'),
            dcc.Store(id='pending-delete-confirm', data=False),
            dcc.Store(id='chat-generating', data=None),
            dcc.Store(id='chat-cancelled', data=None),
            dcc.Store(id='chat-session-id', data=str(uuid.uuid4()), storage_type='memory'),
            # chat-user-id now lives at the top level (build_layout) since it drives
            # the full-page login gate.
            dcc.Store(id='chat-history-tick', data=0),
            dcc.Store(id='chat-sessions-open', data=False),
            dcc.Store(id='chat-menu-open', data=False),
            dcc.Store(id='chat-scroll-target'),
            dcc.Store(id='chat-rename-session-id'),
            dcc.Download(id='download-pdf'),
            dcc.Download(id='download-report'),
            dcc.Store(id='pending-report'),
            html.Div(id='chat-scroll-anchor', style={'display': 'none'}),
            # Transient "Downloaded!" confirmation, blurred over the chat window itself.
            html.Div(
                id='download-overlay',
                className='download-overlay',
                children=[
                    html.Div('Downloaded!', id='download-overlay-text'),
                ],
            ),
            html.Div(
                id='language-selection',
                style={
                    'display': 'flex', 'flexDirection': 'column',
                    'alignItems': 'center', 'justifyContent': 'center',
                    'flex': '1', 'padding': '10px'
                },
                children=[
                    html.Div(
                        'Choose a language / Elige un idioma',
                        style={
                            'fontSize': '14px', 'fontWeight': '600',
                            'marginBottom': '16px', 'textAlign': 'center',
                            'color': '#333'
                        }
                    ),
                    html.Button(
                        'English', id='lang-en-btn',
                        style={
                            'width': '80%', 'padding': '10px 14px',
                            'marginBottom': '10px', 'border': 'none',
                            'borderRadius': '8px', 'cursor': 'pointer',
                            'background': 'linear-gradient(135deg, #03123e 0%, #4b0082 100%)',
                            'color': 'white', 'fontSize': '14px', 'fontWeight': '600'
                        }
                    ),
                    html.Button(
                        'Español', id='lang-es-btn',
                        style={
                            'width': '80%', 'padding': '10px 14px',
                            'border': 'none', 'borderRadius': '8px',
                            'cursor': 'pointer',
                            'background': 'linear-gradient(135deg, #03123e 0%, #4b0082 100%)',
                            'color': 'white', 'fontSize': '14px', 'fontWeight': '600'
                        }
                    ),
                    html.Label(
                        [
                            dcc.Checklist(
                                id='chat-remember-language',
                                options=[{'label': '', 'value': 'remember'}],
                                value=[],
                                inputStyle={'marginRight': '8px'},
                                labelStyle={'display': 'none'},
                                style={'margin': '0'},
                            ),
                            html.Span(
                                'Remember me on this browser',
                                id='chat-remember-language-label',
                                style={'fontSize': '12px', 'color': '#555'},
                            ),
                        ],
                        style={
                            'display': 'flex',
                            'alignItems': 'center',
                            'gap': '6px',
                            'marginTop': '14px',
                        },
                    ),
                ]
            ),
            html.Div(
                id='chat-interface',
                style={
                    'display': 'none', 'flex': '1',
                    'flexDirection': 'column', 'minHeight': '0'
                },
                children=[
                    dcc.Store(id='chat-download-state', data={'downloaded': False}),
                    dcc.Store(id='report-download-state', data={'downloaded': False}),
                    html.Div(
                        [
                            html.Span(
                                'AI Assistant',
                                id='chat-header-label',
                                style={
                                    'fontWeight': 'bold', 'color': '#4b0082',
                                    'fontSize': '14px'
                                },
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        '⋮',
                                        id='chat-menu-btn',
                                        className='chat-menu-btn',
                                        n_clicks=0,
                                        title='Chat options',
                                        style={
                                            'width': '28px',
                                            'height': '28px',
                                            'padding': '0',
                                            'border': 'none',
                                            'borderRadius': '50%',
                                            'background': 'transparent',
                                            'color': '#4b0082',
                                            'fontSize': '20px',
                                            'fontWeight': '700',
                                            'lineHeight': '1',
                                            'cursor': 'pointer',
                                        },
                                    ),
                                    html.Div(
                                        id='chat-menu-dropdown',
                                        style={
                                            'display': 'none',
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
                                        },
                                        children=[
                                            html.Button(
                                                ['🌐 Español'],
                                                id='chat-language-toggle-btn',
                                                className='chat-menu-item',
                                                n_clicks=0,
                                                style=_CHAT_MENU_ITEM_STYLE,
                                            ),
                                            html.Button(
                                                ['Chat History'],
                                                id='chat-sessions-btn',
                                                className='chat-menu-item',
                                                n_clicks=0,
                                                style={**_CHAT_MENU_ITEM_STYLE, 'borderTop': '1px solid #f0eaf6'},
                                            ),
                                            html.Button(
                                                ['＋ New Chat'],
                                                id='chat-new-session-btn',
                                                className='chat-menu-item',
                                                n_clicks=0,
                                                style={**_CHAT_MENU_ITEM_STYLE, 'borderTop': '1px solid #f0eaf6'},
                                            ),
                                            html.Button(
                                                ['⛶ Fit Window'],
                                                id='chat-fit-window-btn',
                                                className='chat-menu-item',
                                                n_clicks=0,
                                                style={**_CHAT_MENU_ITEM_STYLE, 'borderTop': '1px solid #f0eaf6'},
                                            ),
                                            html.Button(
                                                ['Download Chat PDF'],
                                                id='download-pdf-btn',
                                                className='chat-menu-item',
                                                disabled=True,
                                                n_clicks=0,
                                                style={**_CHAT_MENU_ITEM_STYLE, 'borderTop': '1px solid #f0eaf6'},
                                            ),
                                        ],
                                    ),
                                ],
                                style={'position': 'relative'},
                            ),
                        ],
                        style={
                            'display': 'flex',
                            'alignItems': 'center',
                            'justifyContent': 'space-between',
                            'padding': '6px 4px',
                            'paddingRight': '34px',
                            'borderBottom': '1px solid #eee',
                            'marginBottom': '6px',
                        },
                    ),
                    html.Div(
                        id='chat-sessions-panel',
                        children=[
                            html.Div(
                                [
                                    html.Div(
                                        'Your chats',
                                        id='chat-panel-title',
                                        style={
                                            'fontWeight': '700',
                                            'fontSize': '14px',
                                            'color': '#f6edff',
                                        },
                                    ),
                                    dcc.Input(
                                        id='chat-session-search',
                                        type='text',
                                        placeholder='Search conversations...',
                                        debounce=False,
                                        style={
                                            'width': '100%',
                                            'padding': '8px 10px',
                                            'borderRadius': '10px',
                                            'border': '1px solid rgba(255,255,255,0.25)',
                                            'backgroundColor': 'rgba(255,255,255,0.92)',
                                            'fontSize': '12px',
                                            'boxSizing': 'border-box',
                                        },
                                    ),
                                    html.Div(
                                        id='chat-session-rename-row',
                                        style={'display': 'none'},
                                        children=[
                                            dcc.Input(
                                                id='chat-session-rename-input',
                                                type='text',
                                                placeholder='Rename conversation...',
                                                style={
                                                    'flex': '1',
                                                    'padding': '8px 10px',
                                                    'borderRadius': '10px',
                                                    'border': '1px solid rgba(255,255,255,0.25)',
                                                    'fontSize': '12px',
                                                },
                                            ),
                                            html.Button(
                                                'Save',
                                                id='chat-session-rename-save-btn',
                                                n_clicks=0,
                                                style={
                                                    'fontSize': '12px',
                                                    'padding': '7px 10px',
                                                    'borderRadius': '8px',
                                                    'border': 'none',
                                                    'background': '#f6edff',
                                                    'color': '#31104f',
                                                    'cursor': 'pointer',
                                                },
                                            ),
                                            html.Button(
                                                'Cancel',
                                                id='chat-session-rename-cancel-btn',
                                                n_clicks=0,
                                                style={
                                                    'fontSize': '12px',
                                                    'padding': '7px 10px',
                                                    'borderRadius': '8px',
                                                    'border': '1px solid rgba(255,255,255,0.3)',
                                                    'background': 'transparent',
                                                    'color': '#f6edff',
                                                    'cursor': 'pointer',
                                                },
                                            ),
                                        ],
                                    ),
                                ],
                                style={
                                    'display': 'flex',
                                    'flexDirection': 'column',
                                    'gap': '10px',
                                    'marginBottom': '10px',
                                },
                            ),
                            html.Div(
                                id='chat-sessions-list',
                                style={
                                    'flex': '1',
                                    'overflowY': 'auto',
                                    'paddingRight': '4px',
                                },
                            ),
                        ],
                        style={'display': 'none'},
                    ),
                    html.Div(
                        id='chat-messages-container',
                        style={
                            'display': 'flex',
                            'flex': '1',
                            'minHeight': '0',
                            'marginBottom': '10px',
                        },
                        children=[
                            html.Div(
                                id='chat-messages',
                                children=[],
                                style={
                                    'flex': '1',
                                    'overflowY': 'auto',
                                    'border': '1px solid #eee',
                                    'padding': '8px',
                                    'borderRadius': '8px',
                                    'backgroundColor': '#fcfbff',
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        id='chat-input-row',
                        style={
                            'display': 'flex', 'alignItems': 'center',
                            'border': '1px solid #ddd', 'borderRadius': '20px',
                            'padding': '5px 10px', 'backgroundColor': '#f9f9f9'
                        },
                        children=[
                            dcc.Input(
                                id='chat-input', type='text', placeholder='Ask something...',
                                style={
                                    'flex': '1', 'border': 'none', 'outline': 'none',
                                    'backgroundColor': 'transparent', 'padding': '8px'
                                }
                            ),
                            html.Button(
                                '➤', id='chat-send-btn',
                                style={
                                    'border': 'none', 'backgroundColor': '#4b0082',
                                    'color': 'white', 'borderRadius': '50%',
                                    'width': '32px', 'height': '32px',
                                    'cursor': 'pointer', 'marginLeft': '5px'
                                }
                            )
                        ]
                    )
                ]
            )
        ]
    )

    return [chat_btn, chat_popup]


_AUTH_INPUT_STYLE = {
    'width': '100%', 'padding': '10px 12px', 'marginBottom': '10px',
    'borderRadius': '10px', 'border': '1px solid #d7c9ea',
    'fontSize': '13px', 'boxSizing': 'border-box',
}
_AUTH_BTN_STYLE = {
    'width': '100%', 'padding': '10px', 'borderRadius': '10px', 'border': 'none',
    'background': '#4b0082', 'color': 'white', 'fontSize': '14px',
    'fontWeight': '600', 'cursor': 'pointer',
}


def _build_login_page(show: bool = True) -> html.Div:
    """Full-page login/signup gate. Covers the entire viewport until the user is
    authenticated; the rest of the site (dashboard, map, chatbot) is hidden behind
    it. This is the site's landing page for anonymous visitors when
    REQUIRE_LOGIN is on. When it is off, the page is hidden until someone
    clicks "Sign in", and a link leads back to the dashboard.
    """
    return html.Div(
        id='login-page',
        style={
            # Shown by default when sign-in is required; a callback hides it
            # once authenticated.
            'position': 'fixed', 'inset': '0', 'zIndex': '1000',
            'display': 'flex' if show else 'none',
            'background': 'linear-gradient(160deg, #f6edff 0%, #eee6fb 100%)',
            'flexDirection': 'column', 'justifyContent': 'center',
            'alignItems': 'center', 'padding': '24px',
        },
        children=[
            html.Div(
                style={
                    'width': '100%', 'maxWidth': '340px', 'padding': '28px',
                    'background': 'white', 'borderRadius': '16px',
                    'boxShadow': '0 18px 48px rgba(75, 0, 130, 0.18)',
                },
                children=[
                    html.Div(
                        'Puerto Rico MHVI',
                        style={
                            'fontWeight': '700', 'fontSize': '18px',
                            'color': '#31104f', 'marginBottom': '4px',
                            'textAlign': 'center',
                        },
                    ),
                    html.Div(
                        'Sign in',
                        id='auth-title',
                        style={
                            'fontWeight': '600', 'fontSize': '14px',
                            'color': '#7a5aa6', 'marginBottom': '18px',
                            'textAlign': 'center',
                        },
                    ),
                    dcc.Input(
                        id='auth-email', type='email', placeholder='Email',
                        autoComplete='username', style=_AUTH_INPUT_STYLE,
                    ),
                    dcc.Input(
                        id='auth-password', type='password', placeholder='Password',
                        autoComplete='current-password', style=_AUTH_INPUT_STYLE,
                    ),
                    dcc.Input(
                        id='auth-confirm', type='password',
                        placeholder='Confirm password',
                        autoComplete='new-password',
                        style={**_AUTH_INPUT_STYLE, 'display': 'none'},  # signup only
                    ),
                    html.Div(
                        id='auth-error',
                        style={
                            'color': 'crimson', 'fontSize': '12px',
                            'minHeight': '16px', 'marginBottom': '8px',
                        },
                    ),
                    html.Button('Log in', id='auth-submit-btn', n_clicks=0,
                                style=_AUTH_BTN_STYLE),
                    html.Div(
                        [
                            html.Span(id='auth-toggle-prompt',
                                      children="No account? ",
                                      style={'fontSize': '12px', 'color': '#555'}),
                            html.Span(
                                'Sign up', id='auth-toggle-link',
                                n_clicks=0,
                                style={
                                    'fontSize': '12px', 'color': '#4b0082',
                                    'fontWeight': '600', 'cursor': 'pointer',
                                },
                            ),
                        ],
                        style={'textAlign': 'center', 'marginTop': '12px'},
                    ),
                    html.Div(
                        html.Span(
                            'Forgot password?', id='forgot-link', n_clicks=0,
                            style={'fontSize': '12px', 'color': '#7a5aa6',
                                   'cursor': 'pointer', 'textDecoration': 'underline'},
                        ),
                        style={'textAlign': 'center', 'marginTop': '10px'},
                    ),
                    # Only when signing in is optional: back to the dashboard.
                    html.Div(
                        html.Span('← Back to the dashboard', id='login-back-link',
                                  n_clicks=0,
                                  style={'fontSize': '12px', 'color': '#7a5aa6',
                                         'cursor': 'pointer'}),
                        style={'textAlign': 'center', 'marginTop': '14px',
                               'display': 'none' if login_required() else 'block'},
                    ),
                    # 'login' or 'signup' — which mode the form is in.
                    dcc.Store(id='auth-mode', data='login'),
                ],
            ),
            _build_forgot_password_card(),
        ],
    )


def _build_forgot_password_card() -> html.Div:
    """Self-service reset card: enter email -> shows the account's security
    question -> answer it + set a new password. Uses the security-answer reset
    logic (no email needed). Hidden until 'Forgot password?' is clicked."""
    return html.Div(
        id='forgot-card',
        style={
            'display': 'none',  # toggled by the forgot-link callback
            'width': '100%', 'maxWidth': '340px', 'padding': '28px',
            'marginTop': '16px', 'background': 'white', 'borderRadius': '16px',
            'boxShadow': '0 18px 48px rgba(75, 0, 130, 0.18)',
        },
        children=[
            html.Div('Reset your password', style={'fontWeight': '700',
                     'fontSize': '15px', 'color': '#31104f', 'marginBottom': '14px',
                     'textAlign': 'center'}),
            dcc.Input(id='forgot-email', type='email', placeholder='Your email',
                      autoComplete='username', style=_AUTH_INPUT_STYLE),
            html.Button('Find my security question', id='forgot-lookup-btn',
                        n_clicks=0, style=_AUTH_BTN_STYLE),
            # Revealed once a security question is found for the email.
            html.Div(
                id='forgot-step2',
                style={'display': 'none', 'marginTop': '14px'},
                children=[
                    html.Div(id='forgot-question',
                             style={'fontSize': '13px', 'fontWeight': '600',
                                    'color': '#4b0082', 'marginBottom': '8px'}),
                    dcc.Input(id='forgot-answer', type='text', placeholder='Your answer',
                              style=_AUTH_INPUT_STYLE),
                    dcc.Input(id='forgot-newpw', type='password',
                              placeholder='New password', autoComplete='new-password',
                              style=_AUTH_INPUT_STYLE),
                    html.Button('Reset password', id='forgot-reset-btn', n_clicks=0,
                                style=_AUTH_BTN_STYLE),
                ],
            ),
            html.Div(id='forgot-msg',
                     style={'fontSize': '12px', 'minHeight': '16px',
                            'marginTop': '10px', 'color': '#7a5aa6',
                            'textAlign': 'center'}),
            html.Div(
                html.Span('← Back to sign in', id='forgot-back', n_clicks=0,
                          style={'fontSize': '12px', 'color': '#7a5aa6',
                                 'cursor': 'pointer'}),
                style={'textAlign': 'center', 'marginTop': '12px'},
            ),
        ],
    )


