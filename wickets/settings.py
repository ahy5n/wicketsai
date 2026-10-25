"""Load KEY=value lines from the project's .env (git-ignored) without overriding the environment."""
import os

from .db import ROOT


def load_dotenv(paths=(ROOT / ".env.local", ROOT / ".env")):
    """.env.local (never committed: put ANTHROPIC_API_KEY here) wins over .env (committed in this repo)."""
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            key, _, value = line.partition("=")
            key = key.strip()
            if key and not key.startswith("#") and value.strip():
                os.environ.setdefault(key, value.strip().strip('"'))


def require_api_key():
    load_dotenv()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("No Anthropic credentials: add ANTHROPIC_API_KEY=... to .env.local in the project folder.")
