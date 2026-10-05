from urllib.parse import quote
from flask import Blueprint, request, jsonify

from supabase_helper import supabase_request

data_bp = Blueprint('data', __name__)

ALLOWED_TABLES = [
    'patients', 'appointments', 'staff',
    'queue_state', 'queue_stations', 'queue_activity',
    'schedules', 'announcements', 'services',
]


def json_response(data, status=200):
    return jsonify(data), status


def get_bearer_token():
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        return header[7:]
    return None


@data_bp.route('/api/public/queue-status', methods=['GET'])
def public_queue_status():
    """Public TV queue status, separated per doctor while keeping the old fallback."""

    # Ini nagahimo sang A, B, C ... AA prefix halin sa permanent staff ID.
    def queue_prefix(staff_id):
        try:
            number = int(staff_id)
        except (TypeError, ValueError):
            return None
        if number < 1:
            return None
        prefix = ''
        while number > 0:
            number -= 1
            prefix = chr(65 + (number % 26)) + prefix
            number //= 26
        return prefix

    # Ini nagakuha sang numeric part sang A-0, B-2 kag iban pa para insakto ang sorting.
    def queue_value(queue_number):
        try:
            return int(str(queue_number).split('-')[-1])
        except (TypeError, ValueError):
            return 999999999

    # Kuhaon ang existing doctors kag appointments; wala kita nagadugang sang bag-o nga endpoint.
    staff_status, staff_rows = supabase_request(
        'GET',
        '/rest/v1/staff?select=id,name,role,dept'
    )
    appointment_status, appointment_rows = supabase_request(
        'GET',
        '/rest/v1/appointments?select=id,doctor_name,service,status,queue_number'
    )
    station_status, station_rows = supabase_request(
        'GET',
        '/rest/v1/queue_stations?select=id,name,status,doctor_id,doctor_name&order=sort_order.asc'
    )
    if station_status >= 400:
        station_rows = []

    # Kon indi mabasa ang doctor data, gamiton gihapon ang daan nga single queue response.
    if staff_status >= 400 or appointment_status >= 400:
        status, res = supabase_request(
            'GET',
            '/rest/v1/queue_state?id=eq.1&select=current_number,next_number,waiting,current_patient,current_service'
        )
        if status >= 400 or not res:
            return json_response({'error': 'Could not load queue status.'}, 500)
        row = res[0] if isinstance(res, list) and res else {}
        return json_response(row)

    staff_rows = staff_rows if isinstance(staff_rows, list) else []
    appointment_rows = appointment_rows if isinstance(appointment_rows, list) else []
    station_rows = station_rows if isinstance(station_rows, list) else []
    doctors = []
    doctor_rows = [row for row in staff_rows if 'doctor' in str(row.get('role') or '').lower()]
    doctor_rows.sort(key=lambda row: int(row.get('id') or 0))

    # Tagsa ka doctor may kaugalingon nga current, next, waiting kag assigned room.
    for doctor_index, doctor in enumerate(doctor_rows, start=1):
        doctor_id = doctor.get('id')
        doctor_name = str(doctor.get('name') or '').strip()
        if not doctor_id or not doctor_name:
            continue
        prefix = queue_prefix(doctor_index)
        if not prefix:
            continue

        doctor_appointments = []
