import os
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


# Ini nagacheck kon Doctor ukon Medical Doctor gid ang role.
def is_doctor_role(role):
    role = str(role or '').strip().lower()
    return role in ('doctor', 'medical doctor')


# Ini nagacheck sang common staff fields para makita ang doctor bisan lain ang field nga gin-gamit sa record.
def is_doctor_staff(person):
    if not isinstance(person, dict):
        return False

    return any(
        is_doctor_role(person.get(field))
        for field in (
            'role',
            'staff_role',
            'job_role',
            'position',
            'department',
            'dept',
            'specialty',
            'specialization',
        )
    )


# Ini nagakuha sang backend service key para mabasa sang public TV endpoint ang staff bisan may Supabase RLS.
def get_service_token():
    return (
        os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        or os.getenv('SUPABASE_SERVICE_KEY')
        or os.getenv('SUPABASE_SERVICE_ROLE')
        or None
    )


# Ini nagahimo sang A, B, C ... Z, AA, AB depende sa doctor order.
def doctor_prefix(index):
    number = index + 1
    result = ''

    while number > 0:
        number -= 1
        result = chr(65 + (number % 26)) + result
        number //= 26

    return result


# Ini nagakuha sang number sa A-1, A-2, B-1 para insakto ang queue sorting.
def queue_sequence(queue_number):
    try:
        return int(str(queue_number).split('-')[-1])
    except (TypeError, ValueError):
        return 999999999


# Ini nagakuha sang station name bisan lain-lain gamay ang column name sa table.
def get_station_name(station):
    return (
        station.get('name')
        or station.get('station_name')
        or station.get('room_name')
        or station.get('room')
        or station.get('label')
    )


# Ini nagacheck kon ang station naka-assign sa sini nga doctor.
def station_belongs_to_doctor(station, doctor):
    doctor_id = doctor.get('id')
    doctor_name = str(doctor.get('name') or '').strip().lower()

    station_doctor_id = (
        station.get('doctor_id')
        or station.get('staff_id')
        or station.get('assigned_doctor_id')
    )

    station_doctor_name = str(
        station.get('doctor_name')
        or station.get('assigned_doctor')
        or station.get('assigned_to')
        or ''
    ).strip().lower()

    if station_doctor_id is not None and doctor_id is not None:
        if str(station_doctor_id) == str(doctor_id):
            return True

    if station_doctor_name and doctor_name:
        if station_doctor_name == doctor_name:
            return True

    return False


@data_bp.route('/api/public/queue-status', methods=['GET'])
def public_queue_status():
    """
    No login required — this is what the RHU's waiting-room TV display
    calls.

    The new logic returns separate queues for every Doctor / Medical Doctor.
    If the new tables cannot be read, it falls back to the original
    queue_state response so the older TV behavior is still preserved.
    """

    try:
        # Ini ang server-side service token para ang public TV endpoint makabasa sang staff bisan naka-enable ang RLS.
        service_token = get_service_token()

        # Ini nagakuha sang staff, appointments kag stations para makahimo sang per-doctor queue.
        staff_status, staff_res = supabase_request(
            'GET',
            '/rest/v1/staff?select=*&order=id.asc',
            None,
            service_token
        )

        appointment_status, appointment_res = supabase_request(
            'GET',
            '/rest/v1/appointments?select=*',
            None,
            service_token
        )

        station_status, station_res = supabase_request(
            'GET',
            '/rest/v1/queue_stations?select=*',
            None,
            service_token
        )

        # Kon indi mabasa ang staff ukon appointments, balik kita sa original queue_state.
        if staff_status >= 400 or appointment_status >= 400:
            status, res = supabase_request(
                'GET',
                '/rest/v1/queue_state?id=eq.1&select=current_number,next_number,waiting,current_patient,current_service',
                None,
                service_token
            )

            if status >= 400 or not res:
                return json_response(
                    {'error': 'Could not load queue status.'},
                    500
                )

            row = res[0] if isinstance(res, list) and res else {}
            return json_response(row)

        staff_rows = staff_res if isinstance(staff_res, list) else []
        appointment_rows = (
            appointment_res
            if isinstance(appointment_res, list)
            else []
        )

        # Kon wala pa station columns/table access, indi sini pagubaon ang queue.
        station_rows = (
            station_res
            if station_status < 400 and isinstance(station_res, list)
            else []
        )

        # Doctor kag Medical Doctor lang ang masulod diri; Staff/Admin indi included.
        doctors_only = [
            person
            for person in staff_rows
            if is_doctor_staff(person)
        ]

        # Ginasecure naton nga stable ang order sang doctors suno sa staff ID.
        def safe_staff_id(person):
            try:
                return int(person.get('id'))
            except (TypeError, ValueError):
                return 999999999

        doctors_only.sort(key=safe_staff_id)

        doctors = []

        # Tagsa ka doctor may kaugalingon nga current, next, waiting kag station.
        for doctor_index, doctor in enumerate(doctors_only):
            doctor_id = doctor.get('id')
            doctor_name = str(
                doctor.get('name')
                or doctor.get('full_name')
                or doctor.get('doctor_name')
                or ''
            ).strip()

            if not doctor_name:
                continue

            prefix = doctor_prefix(doctor_index)

            doctor_appointments = []

            for appointment in appointment_rows:
                appointment_doctor_id = (
                    appointment.get('doctor_id')
                    or appointment.get('staff_id')
                )

                appointment_doctor_name = str(
                    appointment.get('doctor_name')
                    or appointment.get('doctor')
                    or ''
                ).strip().lower()

                same_doctor = False

                # Kon may doctor_id sa appointment, amo ini ang priority.
                if appointment_doctor_id is not None and doctor_id is not None:
                    same_doctor = (
                        str(appointment_doctor_id) == str(doctor_id)
                    )

                # Para compatible gihapon sa older appointments nga doctor_name lang ang ara.
                if not same_doctor and appointment_doctor_name:
                    same_doctor = (
                        appointment_doctor_name
                        == doctor_name.lower()
                    )

                if not same_doctor:
                    continue

                queue_number = (
                    appointment.get('queue_number')
                    or appointment.get('queueNumber')
                )

                if not queue_number:
                    continue

                appointment_state = str(
                    appointment.get('status') or ''
                ).strip().lower()

                # Approved = waiting, Serving = current.
                if appointment_state not in ('approved', 'serving'):
                    continue

                doctor_appointments.append(appointment)

            # A-1 antes A-2, A-2 antes A-10, indi alphabetical sorting.
            doctor_appointments.sort(
                key=lambda item: queue_sequence(
                    item.get('queue_number')
                    or item.get('queueNumber')
                )
            )

            serving = next(
                (
                    appointment
                    for appointment in doctor_appointments
                    if str(
                        appointment.get('status') or ''
                    ).strip().lower() == 'serving'
                ),
                None
            )

            waiting_list = [
                appointment
                for appointment in doctor_appointments
                if str(
                    appointment.get('status') or ''
                ).strip().lower() == 'approved'
            ]

            # Pangitaon ang room/station nga naka-assign sa sini nga doctor.
            assigned_station = next(
                (
                    station
                    for station in station_rows
                    if station_belongs_to_doctor(station, doctor)
                ),
                None
            )

            station_name = (
                get_station_name(assigned_station)
                if assigned_station
                else None
            )

            station_status_value = (
                assigned_station.get('status')
                if assigned_station
                else None
            )

            current_number = None
            current_service = None

            if serving:
                current_number = (
                    serving.get('queue_number')
                    or serving.get('queueNumber')
                )

                current_service = (
                    serving.get('service')
                    or serving.get('service_name')
                )

            next_number = None

            if waiting_list:
                next_number = (
                    waiting_list[0].get('queue_number')
                    or waiting_list[0].get('queueNumber')
                )

            doctors.append({
                'doctor_id': doctor_id,
                'doctor_name': doctor_name,
                'role': doctor.get('role'),
                'position': doctor.get('position'),
                'department': (
                    doctor.get('department')
                    or doctor.get('specialty')
                    or doctor.get('position')
                    or 'Medical Doctor'
                ),
                'prefix': prefix,
                'current_number': current_number,
                'current_service': current_service,
                'next_number': next_number,
                'waiting': len(waiting_list),
                'station': station_name,
                'station_status': station_status_value
            })

        return json_response({
            'doctors': doctors
        })

    except Exception as error:
        print('PUBLIC QUEUE STATUS ERROR:', error)

        # Kon may unexpected error sa bag-o nga logic, gamiton gihapon ang original queue_state.
        try:
            status, res = supabase_request(
                'GET',
                '/rest/v1/queue_state?id=eq.1&select=current_number,next_number,waiting,current_patient,current_service',
                None,
                get_service_token()
            )

            if status < 400 and res:
                row = (
                    res[0]
                    if isinstance(res, list) and res
                    else {}
                )
                return json_response(row)

        except Exception as fallback_error:
            print(
                'QUEUE STATUS FALLBACK ERROR:',
                fallback_error
            )

        return json_response(
            {'error': 'Could not load queue status.'},
            500
        )


@data_bp.route('/api/data', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def data_proxy():
    token = get_bearer_token()
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
        method = 'PATCH'
    elif method == 'DELETE':
        extra_headers['Prefer'] = 'return=representation'
    else:
        return json_response({'error': 'Method not allowed'}, 405)

    status, res = supabase_request(method, path, body, token, extra_headers)
    return json_response(res, status or 200)
