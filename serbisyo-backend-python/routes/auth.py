import hmac
from urllib.parse import quote
from flask import Blueprint, request, jsonify

from supabase_helper import supabase_request
from config import ADMIN_INVITE_CODE

auth_bp = Blueprint('auth', __name__)


def json_response(data, status=200):
    return jsonify(data), status


def get_bearer_token():
    """Pulls the access token from the Authorization: Bearer <token> header."""
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        return header[7:]
    return None


@auth_bp.route('/api/auth', methods=['GET'])
def auth_session_check():
    """
    Called on app launch to verify a locally-stored token is still valid.
    No server-side session involved — the token itself is the proof.
    """
    if request.args.get('action') == 'session':
        token = get_bearer_token()
        if not token:
            return json_response({'authenticated': False})

        status, res = supabase_request('GET', '/auth/v1/user', token=token)
        if status >= 400 or not res or not res.get('id'):
            return json_response({'authenticated': False})

        return json_response({'authenticated': True, 'user': res})

    return json_response({'error': 'Unknown action.'}, 400)


@auth_bp.route('/api/auth', methods=['POST'])
def auth_actions():
    body = request.get_json(silent=True) or {}
    action = body.get('action', '')

    if action == 'login':
        email = (body.get('email') or '').strip()
        password = body.get('password') or ''
        if not email or not password:
            return json_response({'error': 'Email and password are required.'}, 400)

        status, res = supabase_request('POST', '/auth/v1/token?grant_type=password',
                                        {'email': email, 'password': password})
        if status >= 400 or not res or not res.get('access_token'):
            msg = (res or {}).get('error_description') or (res or {}).get('msg') or (res or {}).get('error') or 'Invalid credentials.'
            return json_response({'error': msg}, 401)

        # The token itself is handed back to the app to store locally —
        # nothing is remembered server-side, so this works correctly even
        # when the frontend and backend are on completely different domains
        # (no reliance on cookies, which mobile browsers often block
        # cross-site anyway).
        return json_response({
            'authenticated': True,
            'user': res['user'],
            'access_token': res['access_token'],
            'refresh_token': res.get('refresh_token'),
        })

    if action == 'signup':
        email = (body.get('email') or '').strip()
        password = body.get('password') or ''
        name = (body.get('name') or '').strip()

        wants_staff = body.get('role') == 'staff'
        invite_code = str(body.get('invite_code') or '')
        code_matches = (
            bool(ADMIN_INVITE_CODE)
            and ADMIN_INVITE_CODE != 'CHANGE-THIS-SECRET-CODE'
            and hmac.compare_digest(ADMIN_INVITE_CODE, invite_code)
        )
        role = 'staff' if (wants_staff and code_matches) else 'patient'

        if wants_staff and not code_matches:
            return json_response({'error': 'Invalid or missing staff invite code.'}, 403)
        if not email or not password or not name:
            return json_response({'error': 'All fields are required.'}, 400)
        if len(password) < 6:
            return json_response({'error': 'Password must be at least 6 characters.'}, 400)

        status, res = supabase_request('POST', '/auth/v1/signup', {
            'email': email, 'password': password, 'data': {'name': name, 'role': role}
        })
        if status >= 400:
            msg = (res or {}).get('error_description') or (res or {}).get('msg') or (res or {}).get('error') or 'Could not create account.'
            return json_response({'error': msg}, 400)

        if res and res.get('access_token'):
            return json_response({
                'authenticated': True,
                'user': res['user'],
                'access_token': res['access_token'],
                'refresh_token': res.get('refresh_token'),
            })

        return json_response({'authenticated': False, 'message': 'Account created. Check your email to confirm it, then log in.'})

    if action == 'logout':
        # No server-side session to clear. Best-effort: tell Supabase to
        # invalidate the refresh token too, if one was provided.
        token = get_bearer_token()
        if token:
            supabase_request('POST', '/auth/v1/logout', token=token)
        return json_response({'ok': True})

    if action == 'forgot_password':
        email = (body.get('email') or '').strip()
        redirect_to = (body.get('redirect_to') or '').strip()
        if not email:
            return json_response({'error': 'Email is required.'}, 400)
        if not redirect_to:
            return json_response({'error': 'Missing redirect URL.'}, 400)

        status, res = supabase_request(
            'POST', f'/auth/v1/recover?redirect_to={quote(redirect_to, safe="")}',
            {'email': email}
        )
        if status >= 400:
            msg = (res or {}).get('error_description') or (res or {}).get('msg') or (res or {}).get('error') or 'Could not send reset email.'
            return json_response({'error': msg}, 400)

        return json_response({'ok': True, 'message': 'If that email is registered, a reset link has been sent.'})

    if action == 'update_password':
        access_token = (body.get('access_token') or '').strip()
        new_password = body.get('password') or ''
        if not access_token:
            return json_response({'error': 'Missing or expired reset link.'}, 400)
        if len(new_password) < 6:
            return json_response({'error': 'Password must be at least 6 characters.'}, 400)

        status, res = supabase_request('PUT', '/auth/v1/user', {'password': new_password}, token=access_token)
        if status >= 400:
            msg = (res or {}).get('error_description') or (res or {}).get('msg') or (res or {}).get('error') or 'Could not update password.'
            return json_response({'error': msg}, 400)

        return json_response({'ok': True})

    return json_response({'error': 'Unknown action.'}, 400)
