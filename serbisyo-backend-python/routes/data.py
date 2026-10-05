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
    doctors = []

    # Tagsa ka doctor may kaugalingon nga current, next kag waiting count.
    for doctor in staff_rows:
        if 'doctor' not in str(doctor.get('role') or '').lower():
            continue
        doctor_id = doctor.get('id')
        doctor_name = str(doctor.get('name') or '').strip()
        if not doctor_id or not doctor_name:
            continue
        prefix = queue_prefix(doctor_id)
        if not prefix:
            continue

        doctor_appointments = []
        for appointment in appointment_rows:
            if str(appointment.get('doctor_name') or '').strip().lower() != doctor_name.lower():
                continue
            if not appointment.get('queue_number'):
                continue
            status_name = str(appointment.get('status') or '').strip().lower()
            if status_name not in ('approved', 'serving'):
