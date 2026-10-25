"""Load KEY=value lines from the project's .env (git-ignored) without overriding the environment."""
import os

from .db import ROOT


def load_dotenv(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, _, value = line.partition("=")
        key = key.strip()
        if key and not key.startswith("#") and value.strip():
            os.environ.setdefault(key, value.strip().strip('"'))


def require_api_key():
    load_dotenv()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("No Anthropic credentials: add ANTHROPIC_API_KEY=... to .env in the project folder.")
