import uuid
import requests
from flask import Blueprint, request, jsonify

from config import SUPABASE_URL, SUPABASE_ANON_KEY

upload_bp = Blueprint('upload', __name__)

ALLOWED_EXT = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
               'gif': 'image/gif', 'webp': 'image/webp'}
MAX_BYTES = 5 * 1024 * 1024  # 5MB
BUCKET = 'schedule-images'


def json_response(data, status=200):
    return jsonify(data), status


def get_bearer_token():
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        return header[7:]
    return None


@upload_bp.route('/api/upload', methods=['POST'])
def upload_image():
    """
    Uploads a schedule's poster/photo to a public Supabase Storage
    bucket and returns its public URL, which gets saved onto the
    schedule row (image_url column) and shown in both the admin
    panel and, later, the mobile app's Activities list.
    """
    token = get_bearer_token()
    if not token:
        return json_response({'error': 'Not authenticated. Please log in.'}, 401)

    if 'file' not in request.files:
        return json_response({'error': 'No file provided.'}, 400)

    file = request.files['file']
    filename = file.filename or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    content_type = ALLOWED_EXT.get(ext) or file.mimetype

    if ext not in ALLOWED_EXT and content_type not in ALLOWED_EXT.values():
        return json_response({'error': 'Only PNG, JPG, GIF, or WEBP images are allowed.'}, 400)

    data = file.read()
    if len(data) > MAX_BYTES:
        return json_response({'error': 'Image is too large (max 5MB).'}, 400)
    if len(data) == 0:
        return json_response({'error': 'That file appears to be empty.'}, 400)

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return json_response({'error': 'Backend is not configured yet. Set SUPABASE_URL and SUPABASE_ANON_KEY as environment variables in Render.'}, 500)

    object_path = f"{uuid.uuid4().hex}.{ext or 'jpg'}"
    upload_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"

    try:
        resp = requests.post(
            upload_url,
            headers={
                'apikey': SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {token}',
                'Content-Type': content_type or 'application/octet-stream',
            },
            data=data,
            timeout=30,
        )
    except requests.RequestException as e:
        return json_response({'error': f'Could not reach storage: {e}'}, 502)

    if resp.status_code >= 400:
        try:
            err = resp.json()
        except ValueError:
            err = {}
        msg = err.get('message') or err.get('error') or f'Upload failed ({resp.status_code}). Make sure the "{BUCKET}" storage bucket exists and is public — see SETUP for the SQL storage policies.'
        return json_response({'error': msg}, resp.status_code if resp.status_code < 500 else 502)

    public_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{BUCKET}/{object_path}"
    return json_response({'url': public_url})
