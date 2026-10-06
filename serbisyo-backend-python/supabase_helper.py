import os
import requests
from config import SUPABASE_URL, SUPABASE_ANON_KEY


# Ini nagakuha sang secure service-role key halin sa Render environment kon kinahanglan sang trusted backend read.
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')


def supabase_request(method, path, body=None, token=None, extra_headers=None):
    """
    Sends a request to Supabase (REST or Auth API).
    Pass the signed-in user's access token to run the request AS that user
    (so Supabase's row-level security policies apply normally). Omit it to
    fall back to the anon key (used for login/signup, which don't need it).
    Returns (status_code, parsed_json_or_none).
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return 500, {'error': 'Backend is not configured yet. Set SUPABASE_URL and SUPABASE_ANON_KEY as environment variables in Render.'}

    url = SUPABASE_URL.rstrip('/') + path

    # Ini nagapili sang auth key: user token kon may ara, otherwise anon key pareho sang original behavior.
    auth_key = token or SUPABASE_ANON_KEY

    # Ini nagagamit sang service-role key bilang apikey kon amo ini ang token nga ginpasa sang trusted backend route.
    api_key = (
        SUPABASE_SERVICE_ROLE_KEY
        if SUPABASE_SERVICE_ROLE_KEY and auth_key == SUPABASE_SERVICE_ROLE_KEY
        else SUPABASE_ANON_KEY
    )

    headers = {
        'apikey': api_key,
        'Authorization': f'Bearer {auth_key}',
        'Content-Type': 'application/json',
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        resp = requests.request(method, url, headers=headers, json=body, timeout=20)
    except requests.RequestException as e:
        return 502, {'error': f'Could not reach Supabase: {e}'}

    try:
        data = resp.json()
    except ValueError:
        data = None  # e.g. empty body on some DELETEs

    return resp.status_code, data
