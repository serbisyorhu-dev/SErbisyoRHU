import os

# ============================================================
# All values come from environment variables, set in Render's
# dashboard (Settings → Environment) — NEVER committed to GitHub.
# See .env.example for the full list you need to set.
# ============================================================

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
ADMIN_INVITE_CODE = os.environ.get('ADMIN_INVITE_CODE', '')

# Signs/encrypts the session cookie. Generate a real random one for
# production — e.g. run: python -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', '')

# Your deployed Vercel frontend URL, e.g. https://serbisyo-rhu.vercel.app
# Must be exact (no trailing slash) — CORS will reject requests from
# anywhere else once this is set to a real value.
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')
