from urllib.parse import quote
from flask import Blueprint, request, session, jsonify

from supabase_helper import supabase_request

data_bp = Blueprint('data', __name__)

ALLOWED_TABLES = [
    'patients', 'appointments', 'staff',
    'queue_state', 'queue_stations', 'queue_activity',
    'schedules', 'announcements', 'services',
]


def json_response(data, status=200):
    return jsonify(data), status


@data_bp.route('/api/data', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def data_proxy():
    token = session.get('access_token')
    if not token:
        return json_response({'error': 'Not authenticated. Please log in.'}, 401)

    table = request.args.get('table', '')
    if table not in ALLOWED_TABLES:
        return json_response({'error': f'Unknown or disallowed table: {table}'}, 400)

    query = []
    row_id = request.args.get('id')
    if row_id is not None:
        query.append('id=eq.' + quote(row_id, safe=''))

    eq = request.args.get('eq')
    if eq and '.' in eq:
        col, val = eq.split('.', 1)
        query.append(f'{quote(col, safe="")}=eq.{quote(val, safe="")}')

    order = request.args.get('order')
    if order:
        query.append('order=' + quote(order, safe='.,'))

    limit = request.args.get('limit')
    if limit:
        try:
            query.append('limit=' + str(int(limit)))
        except ValueError:
            pass

    path = f'/rest/v1/{table}'
    if query:
        path += '?' + '&'.join(query)

    method = request.method
    body = None
    extra_headers = {}

    if method == 'GET':
        pass
    elif method == 'POST':
        body = request.get_json(silent=True) or {}
        extra_headers['Prefer'] = 'return=representation'
    elif method in ('PUT', 'PATCH'):
        body = request.get_json(silent=True) or {}
        extra_headers['Prefer'] = 'return=representation'
        method = 'PATCH'  # PostgREST always uses PATCH for partial updates
    elif method == 'DELETE':
        extra_headers['Prefer'] = 'return=representation'
    else:
        return json_response({'error': 'Method not allowed'}, 405)

    status, res = supabase_request(method, path, body, token, extra_headers)
    return json_response(res, status or 200)
