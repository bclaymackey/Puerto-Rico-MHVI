"""Is signing in required to use the site?

One switch, set in .env locally or in the Hugging Face Space's settings:

    REQUIRE_LOGIN=1   the site opens on the sign-in page (the AI-CHATBOT
                      branch's original behaviour, and the default)
    REQUIRE_LOGIN=0   anyone can use the dashboard and the assistant; a
                      "Sign in" button in the header lets people sign in to keep
                      their chat history and report issues

Nothing else needs to change to switch between the two — restart the app (or
the Space) after changing the value.
"""

import os

from dotenv import load_dotenv

load_dotenv()

_OFF = {"0", "false", "no", "off"}


def login_required() -> bool:
    return os.getenv("REQUIRE_LOGIN", "1").strip().lower() not in _OFF
