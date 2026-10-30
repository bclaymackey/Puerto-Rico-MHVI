"""The MHVI dashboard (map, right-hand panel, tables, Data Dictionary, Custom
Report Builder) as a package the main app plugs in.

    from dashboard import dashboard_children, register_dashboard_callbacks

See core.py for the file-by-file overview.
"""
from .layout import dashboard_children
from .callbacks import register_dashboard_callbacks
from .chat_bridge import answer_question, grounded_bubble
from .core import encode_image, global_categories

__all__ = [
    "dashboard_children",
    "register_dashboard_callbacks",
    "answer_question",
    "grounded_bubble",
    "encode_image",
    "global_categories",
]
