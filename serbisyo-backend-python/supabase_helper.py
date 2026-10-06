import requests
from config import SUPABASE_URL, SUPABASE_ANON_KEY


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
    headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {token or SUPABASE_ANON_KEY}',
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
