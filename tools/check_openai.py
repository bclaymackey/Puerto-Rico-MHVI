"""Check the OpenAI key the dashboard will use, and explain any error plainly.

    python tools/check_openai.py        (from the project folder)

When the chat says "The AI assistant is currently unavailable.", the real
reason is hidden: the app catches every error and shows that one line.
This script makes the same kind of request the app makes and tells you which
of the usual problems it is.

It never prints your key — only its first few characters and last four.
It sends one very small request (a fraction of a cent).
"""
import os
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = APP_DIR / '.env'


def mask(key):
    if not key:
        return '(none)'
    key = key.strip()
    m = re.match(r'(sk-[a-z]+-|sk-)', key)
    head = m.group(0) if m else key[:3]
    return f"{head}…{key[-4:]}  ({len(key)} characters)"


def model_used_by_app(file_values):
    """The model the app will ask for: OPENAI_MODEL from the environment or
    .env, else the default in chat/hyperparameters.py."""
    model = os.environ.get('OPENAI_MODEL') or file_values.get('OPENAI_MODEL')
    if model:
        return model.strip()
    try:
        src = (APP_DIR / 'chat' / 'hyperparameters.py').read_text(encoding='utf-8')
        m = re.search(r'OPENAI_MODEL",\s*"([^"]+)"', src)
        if m:
            return m.group(1)
    except OSError:
        pass
    return '(unknown)'


def explain(title, *lines):
    print(f"\n  ✗ {title}")
    for line in lines:
        print(f"    {line}")


print("OpenAI key check for the MHVI dashboard\n")

# ---------------------------------------------------------------------------
# 1. Which key will the app actually use?
# ---------------------------------------------------------------------------
try:
    from dotenv import dotenv_values
except ImportError:
    print("python-dotenv is not installed: pip install python-dotenv")
    sys.exit(1)

system_key = os.environ.get('OPENAI_API_KEY')
file_key = None
file_values = {}
if ENV_PATH.is_file():
    file_values = dotenv_values(ENV_PATH)
    file_key = file_values.get('OPENAI_API_KEY')
    print(f"  .env file            : found  ({ENV_PATH})")
    print(f"  key in .env          : {mask(file_key)}")
else:
    print(f"  .env file            : NOT FOUND at {ENV_PATH}")

print(f"  key in your system   : {mask(system_key)}")

# load_dotenv() — what the app calls — does NOT override a variable that is
# already set. So a key in your Windows environment silently wins over .env.
if system_key and file_key and system_key.strip() != file_key.strip():
    explain(
        "Your computer has its own OPENAI_API_KEY, and it is overriding .env",
        "The app uses the system key above, not the new one in .env.",
        "Fix: Start menu → 'Edit environment variables for your account' →",
        "delete OPENAI_API_KEY → close and reopen your terminal.",
        "(For this terminal only: PowerShell  Remove-Item Env:OPENAI_API_KEY",
        " or Command Prompt  set OPENAI_API_KEY=)",
    )
effective = (system_key or file_key or '').strip()
if not effective:
    explain("No key found",
            "Create .env in the project folder (copy .env.example) and paste the key "
            "after OPENAI_API_KEY=")
    sys.exit(1)
print(f"  key the app will use : {mask(effective)}")

model = model_used_by_app(file_values)
print(f"  model the app uses   : {model}")
provider = (os.environ.get('LLM_PROVIDER') or file_values.get('LLM_PROVIDER')
            or 'ollama').strip().lower()
print(f"  LLM_PROVIDER         : {provider}")
if provider != 'openai':
    explain("LLM_PROVIDER is not 'openai'",
            "The app will try a local Ollama model, not OpenAI, so this key",
            "is not used. Set LLM_PROVIDER=openai in .env (and in the",
            "Hugging Face Space's variables) to use it.")

# ---------------------------------------------------------------------------
# 2. Make the same kind of request the app makes
# ---------------------------------------------------------------------------
try:
    import openai
    from openai import OpenAI
except ImportError:
    print("\nThe openai package is not installed: pip install openai")
    sys.exit(1)

print(f"  openai package       : {getattr(openai, '__version__', '?')}")
print("\nSending one small test request…")

client = OpenAI(api_key=effective)
if not hasattr(client, 'responses'):
    explain("Your openai package is too old for the API the app uses",
            "Fix: pip install --upgrade openai")
    sys.exit(1)

try:
    client.responses.create(model=model, input="Reply with the word OK.",
                            max_output_tokens=200)
except openai.AuthenticationError as e:
    explain("OpenAI rejected the key (401 — authentication)",
            "The key is wrong, was revoked, or was copied incompletely.",
            "Fix: create a fresh key and paste it into .env in one piece.",
            f"OpenAI said: {e}")
    sys.exit(1)
except openai.PermissionDeniedError as e:
    explain("The key is valid but not allowed to do this (403 — permissions)",
            "Most likely the key was created with 'Restricted' permissions",
            "and the Responses endpoint is not enabled, or the project does",
            f"not allow the model '{model}'.",
            "Fix: in the project's API keys page, set the key's permissions",
            "to 'All' (or enable Write for 'Responses'), and check the",
            "project's allowed models.",
            f"OpenAI said: {e}")
    sys.exit(1)
except openai.RateLimitError as e:
    text = str(e)
    if 'insufficient_quota' in text or 'quota' in text.lower():
        explain("Out of credits or over the project budget (429 — quota)",
                "The key works, but there is nothing left to spend. Either",
                "the organization's credit balance is $0, or the project's",
                "monthly budget is set to $0 or has been reached.",
                "Fix: add credits under Settings → Billing, and/or raise the",
                "project's monthly budget under the project's Limits page.",
                "New credits can take a few minutes to apply.",
                f"OpenAI said: {e}")
    else:
        explain("Too many requests in a short time (429 — rate limit)",
                "Wait a minute and try again.",
                f"OpenAI said: {e}")
    sys.exit(1)
except openai.NotFoundError as e:
    explain(f"The model '{model}' is not available to this project (404)",
            "Fix: check the project's allowed models in its settings.",
            f"OpenAI said: {e}")
    sys.exit(1)
except (openai.APIConnectionError, openai.APITimeoutError) as e:
    explain("Could not reach OpenAI (network)",
            "Check your internet connection, VPN or firewall.",
            f"Details: {e}")
    sys.exit(1)
except openai.APIError as e:
    explain("OpenAI returned an error",
            f"OpenAI said: {e}")
    sys.exit(1)

print("\n  ✓ The key works. The dashboard's assistant should respond.")
print("    If the chat still says 'unavailable', restart the app — it reads")
print("    the key once, when it starts.")
sys.exit(0)
