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


# Ini nagakuha sang backend service key kon kinahanglan sa iban nga trusted backend function.
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


# Ini ang public TV route nga naga-call sang safe Supabase function kag wala kinahanglan login.
@data_bp.route('/api/public/queue-status', methods=['GET'])
def public_queue_status():
    """
    Public TV endpoint.

    No login is required.
    The Supabase RPC function returns only doctor and queue information,
    without exposing patient-identifying records.
    """

    try:
        # Ini naga-call sang public_doctor_queues() nga gin-test na kag nagabalik sang tanan doctor cards.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/public_doctor_queues',
            {}
        )

        if status >= 400:
            print(
                'PUBLIC DOCTOR QUEUES ERROR:',
                status,
                res
            )

            return json_response(
                {
                    'error': 'Could not load doctor queues.'
                },
                500
            )

        doctors = (
            res
            if isinstance(res, list)
            else []
        )

        # Ini nagabalik sang doctors array bisan wala pa patient ukon active queue.
        return json_response({
            'doctors': doctors
        })

    except Exception as error:
        print(
            'PUBLIC QUEUE STATUS ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not load doctor queues.'
            },
            500
        )


# Ini naga-book sang slot kag appointment sa isa lang ka atomic Supabase transaction.
@data_bp.route('/api/book-appointment', methods=['POST'])
def book_appointment_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    schedule_id = body.get(
        'schedule_id'
    )

    patient_id = body.get(
        'patient_id'
    )

    # Ini nagasiguro nga valid numeric IDs ang ginpadala sang Android app.
    try:
        schedule_id = int(
            schedule_id
        )

        patient_id = int(
            patient_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid schedule and patient are required.'
            },
            400
        )

    try:
        # Ini naga-call sang atomic PostgreSQL function nga naga-lock sang schedule row.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/book_appointment_atomic',
            {
                'p_schedule_id': schedule_id,
                'p_patient_id': patient_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not book this appointment.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            # Ini nga errors ginatreat as booking conflict para makahatag clear message ang Android app.
            conflict_messages = (
                'already full',
                'full',
                'no longer available',
                'past schedules',
                'past schedule',
                'already has an active booking',
                'schedule not found',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Booking was not created.'
                },
                500
            )

        # Android expects one Appointment object, indi list.
        return json_response(
            rows[0],
            201
        )

    except Exception as error:
        print(
            'ATOMIC BOOKING ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not complete the booking.'
            },
            500
        )


# Ini naga-book sang admin walk-in kag naga-reserve sang slot sa isa lang ka atomic transaction.
@data_bp.route('/api/admin/book-appointment', methods=['POST'])
def admin_book_appointment_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    schedule_id = body.get(
        'schedule_id'
    )

    patient_name = str(
        body.get('patient')
        or ''
    ).strip()

    try:
        schedule_id = int(
            schedule_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid schedule is required.'
            },
            400
        )

    if not patient_name:
        return json_response(
            {
                'error': 'Patient name is required.'
            },
            400
        )

    try:
        # Ini naga-call sang separate admin RPC para atomic ang walk-in booking kag slot reservation.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/admin_book_appointment_atomic',
            {
                'p_schedule_id': schedule_id,
                'p_patient': patient_name
            },
            token
        )

        if status >= 400:
            message = (
                'Could not book this walk-in appointment.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'already full',
                'full',
                'no longer available',
                'past schedules',
                'past schedule',
                'schedule not found',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authorized' in normalized_message
                or 'not authenticated' in normalized_message
                or 'staff account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Walk-in booking was not created.'
                },
                500
            )

        # Admin web expects one appointment object, indi list.
        return json_response(
            rows[0],
            201
        )

    except Exception as error:
        print(
            'ADMIN ATOMIC BOOKING ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not complete the walk-in booking.'
            },
            500
        )


# Ini naga-assign sang official queue number sa isa lang ka atomic database transaction.
@data_bp.route('/api/admin/assign-queue', methods=['POST'])
def admin_assign_queue_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    appointment_id = body.get(
        'appointment_id'
    )

    try:
        appointment_id = int(
            appointment_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid appointment is required.'
            },
            400
        )

    try:
        # Ini naga-call sang RPC nga naga-lock kag naga-assign sang next daily queue number.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/admin_assign_queue_atomic',
            {
                'p_appointment_id': appointment_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not assign a queue number.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'already has a queue number',
                'appointment is not pending',
                'appointment is not for today',
                'doctor is required',
                'appointment not found',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authorized' in normalized_message
                or 'not authenticated' in normalized_message
                or 'staff account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Queue number was not assigned.'
                },
                500
            )

        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'ADMIN ATOMIC QUEUE ASSIGN ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not assign the queue number.'
            },
            500
        )


# Ini naga-reset kag naga-renumber sang active doctor queue atomically.
@data_bp.route('/api/admin/reset-queue', methods=['POST'])
def admin_reset_queue_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    doctor_id = body.get(
        'doctor_id'
    )

    try:
        doctor_id = int(
            doctor_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid doctor is required.'
            },
            400
        )

    try:
        # Ini naga-call sang RPC nga naga-lock kag naga-renumber sang active queue sang doctor sa isa ka transaction.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/admin_reset_queue_atomic',
            {
                'p_doctor_id': doctor_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not reset this doctor queue.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'doctor record not found',
                'selected staff member is not a doctor',
                'no active queue to reset',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'staff account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'No active queue to reset.'
                },
                409
            )

        return json_response(
            rows,
            200
        )

    except Exception as error:
        print(
            'ADMIN ATOMIC RESET QUEUE ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not reset this doctor queue.'
            },
            500
        )


# Ini naga-mark No Show sa current patient kag naga-call sang next patient atomically.
@data_bp.route('/api/admin/no-show-next', methods=['POST'])
def admin_no_show_next_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    doctor_id = body.get(
        'doctor_id'
    )

    try:
        doctor_id = int(
            doctor_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid doctor is required.'
            },
            400
        )

    try:
        # Ini naga-call sang RPC nga naga-lock sang doctor queue antes mag-No Show kag Call Next.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/admin_no_show_next_atomic',
            {
                'p_doctor_id': doctor_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not update this doctor queue.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'doctor record not found',
                'selected staff member is not a doctor',
                'no patient is currently being served',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'staff account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        result = (
            res[0]
            if isinstance(res, list) and res
            else res
        )

        if not isinstance(result, dict):
            return json_response(
                {
                    'error': 'Queue update returned no result.'
                },
                500
            )

        return json_response(
            result,
            200
        )

    except Exception as error:
        print(
            'ADMIN ATOMIC NO SHOW NEXT ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not update this doctor queue.'
            },
            500
        )


# Ini naga-recall sang current Serving appointment halin sa admin atomically.
@data_bp.route('/api/admin/recall-current', methods=['POST'])
def admin_recall_current_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    appointment_id = body.get(
        'appointment_id'
    )

    try:
        appointment_id = int(
            appointment_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid appointment is required.'
            },
            400
        )

    try:
        # Ini naga-call sang admin RPC nga naga-verify today kag Serving status antes mag-recall.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/admin_recall_current_atomic',
            {
                'p_appointment_id': appointment_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not recall this patient.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'appointment not found',
                'appointment is not for today',
                'appointment is not currently serving',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'staff account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Patient was not recalled.'
                },
                500
            )

        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'ADMIN ATOMIC RECALL CURRENT ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not recall this patient.'
            },
            500
        )


# Ini naga-call sang next waiting patient sang selected doctor halin sa admin atomically.
@data_bp.route('/api/admin/call-next', methods=['POST'])
def admin_call_next_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    doctor_id = body.get(
        'doctor_id'
    )

    try:
        doctor_id = int(
            doctor_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid doctor is required.'
            },
            400
        )

    try:
        # Ini naga-call sang admin RPC nga naga-lock sang same doctor queue antes mag-call next.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/admin_doctor_call_next_atomic',
            {
                'p_doctor_id': doctor_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not call the next patient.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'doctor record not found',
                'selected staff member is not a doctor',
                'current patient must be completed first',
                'no waiting patients',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'staff account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'No waiting patients.'
                },
                409
            )

        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'ADMIN ATOMIC CALL NEXT ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not call the next patient.'
            },
            500
        )


# Ini nagahimo sang family-member patient record nga naka-link sa logged-in account.
@data_bp.route('/api/family-member', methods=['POST'])
def add_family_member_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    name = str(
        body.get('name')
        or ''
    ).strip()

    relationship = str(
        body.get('relationship')
        or ''
    ).strip()

    contact = str(
        body.get('contact')
        or ''
    ).strip()

    try:
        age = int(
            body.get('age')
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'Enter a valid age.'
            },
            400
        )

    if not name:
        return json_response(
            {
                'error': 'Family member name is required.'
            },
            400
        )

    if not relationship:
        return json_response(
            {
                'error': 'Relationship is required.'
            },
            400
        )

    if age < 0 or age > 130:
        return json_response(
            {
                'error': 'Enter a valid age.'
            },
            400
        )

    try:
        # Ini naga-call sang SECURITY DEFINER RPC para owner_user_id amo gid ang auth.uid().
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/add_family_member_atomic',
            {
                'p_name': name,
                'p_relationship': relationship,
                'p_age': age,
                'p_contact': contact
            },
            token
        )

        if status >= 400:
            message = (
                'Could not add family member.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            if (
                'duplicate' in normalized_message
                or 'already exists' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Family member was not created.'
                },
                500
            )

        return json_response(
            rows[0],
            201
        )

    except Exception as error:
        print(
            'ADD FAMILY MEMBER ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not add family member.'
            },
            500
        )


# Ini nagabalik lang sang appointments nga assigned sa logged-in doctor.
@data_bp.route('/api/doctor/appointments', methods=['GET'])
def doctor_appointments_secure():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    try:
        # Ini naga-call sang RPC para doctor-owned appointments lang gid ang mabalik sa portal.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/doctor_appointments_secure',
            {},
            token
        )

        if status >= 400:
            message = (
                'Could not load doctor appointments.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'doctor account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        return json_response(
            rows,
            200
        )

    except Exception as error:
        print(
            'DOCTOR SECURE APPOINTMENTS ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not load doctor appointments.'
            },
            500
        )


# Ini naga-call sang next waiting patient sang logged-in doctor sa isa lang ka atomic transaction.
@data_bp.route('/api/doctor/call-next', methods=['POST'])
def doctor_call_next_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    try:
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/doctor_call_next_atomic',
            {},
            token
        )

        if status >= 400:
            message = 'Could not call the next patient.'

            if isinstance(res, dict):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'current patient must be completed first',
                'no waiting patients',
                'doctor record not found',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'doctor account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'No waiting patients.'
                },
                409
            )

        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'DOCTOR ATOMIC CALL NEXT ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not call the next patient.'
            },
            500
        )


# Ini naga-recall sang current Serving appointment sang logged-in doctor atomically.
@data_bp.route('/api/doctor/recall-current', methods=['POST'])
def doctor_recall_current_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    appointment_id = body.get(
        'appointment_id'
    )

    try:
        appointment_id = int(
            appointment_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid appointment is required.'
            },
            400
        )

    try:
        # Ini naga-call sang RPC nga naga-verify doctor ownership, today, kag Serving status antes mag-recall.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/doctor_recall_current_atomic',
            {
                'p_appointment_id': appointment_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not recall this patient.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'appointment not found',
                'appointment is not assigned to this doctor',
                'appointment is not for today',
                'appointment is not currently serving',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'doctor account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Patient was not recalled.'
                },
                500
            )

        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'DOCTOR ATOMIC RECALL CURRENT ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not recall this patient.'
            },
            500
        )


# Ini naga-complete sang current Serving appointment sang logged-in doctor atomically.
@data_bp.route('/api/doctor/complete-current', methods=['POST'])
def doctor_complete_current_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    appointment_id = body.get(
        'appointment_id'
    )

    try:
        appointment_id = int(
            appointment_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid appointment is required.'
            },
            400
        )

    try:
        # Ini naga-call sang RPC nga naga-verify doctor ownership, today, kag Serving status antes mag-complete.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/doctor_complete_current_atomic',
            {
                'p_appointment_id': appointment_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not complete this appointment.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'appointment not found',
                'appointment is not assigned to this doctor',
                'appointment is not for today',
                'appointment is not currently serving',
                'appointment is already completed',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'doctor account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Appointment was not completed.'
                },
                500
            )

        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'DOCTOR ATOMIC COMPLETE CURRENT ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not complete this appointment.'
            },
            500
        )


# Ini naga-delete sang appointment sang logged-in doctor kag naga-release sang slot atomically.
@data_bp.route('/api/doctor/delete-appointment', methods=['POST'])
def doctor_delete_appointment_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    appointment_id = body.get(
        'appointment_id'
    )

    try:
        appointment_id = int(
            appointment_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid appointment is required.'
            },
            400
        )

    try:
        # Ini naga-call sang RPC nga naga-verify ownership sang doctor kag naga-release sang slot atomically.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/doctor_delete_appointment_atomic',
            {
                'p_appointment_id': appointment_id
            },
            token
        )

        if status >= 400:
            message = (
                'Could not delete this appointment.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'appointment not found',
                'appointment is not assigned to this doctor',
                'completed appointments cannot be deleted',
                'serving appointments cannot be deleted',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authenticated' in normalized_message
                or 'not authorized' in normalized_message
                or 'doctor account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Appointment was not deleted.'
                },
                500
            )

        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'DOCTOR ATOMIC DELETE APPOINTMENT ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not delete this appointment.'
            },
            500
        )


# Ini naga-cancel ukon naga-delete sang appointment kag naga-release sang schedule slot atomically.
@data_bp.route('/api/admin/release-appointment', methods=['POST'])
def admin_release_appointment_atomic():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    body = (
        request.get_json(
            silent=True
        )
        or {}
    )

    appointment_id = body.get(
        'appointment_id'
    )

    action = str(
        body.get('action')
        or 'cancel'
    ).strip().lower()

    try:
        appointment_id = int(
            appointment_id
        )

    except (
        TypeError,
        ValueError
    ):
        return json_response(
            {
                'error': 'A valid appointment is required.'
            },
            400
        )

    if action not in (
        'cancel',
        'delete'
    ):
        return json_response(
            {
                'error': 'Action must be cancel or delete.'
            },
            400
        )

    try:
        # Ini naga-call sang RPC nga naga-lock sang appointment kag schedule antes mag-release slot.
        status, res = supabase_request(
            'POST',
            '/rest/v1/rpc/admin_release_appointment_atomic',
            {
                'p_appointment_id': appointment_id,
                'p_action': action
            },
            token
        )

        if status >= 400:
            message = (
                'Could not update this appointment.'
            )

            if isinstance(
                res,
                dict
            ):
                message = (
                    res.get('message')
                    or res.get('error')
                    or message
                )

            normalized_message = (
                str(message)
                .strip()
                .lower()
            )

            conflict_messages = (
                'appointment not found',
                'already cancelled',
                'already completed',
                'cannot cancel',
                'cannot delete',
            )

            if any(
                text in normalized_message
                for text in conflict_messages
            ):
                return json_response(
                    {
                        'error': message
                    },
                    409
                )

            if (
                'not authorized' in normalized_message
                or 'not authenticated' in normalized_message
                or 'staff account' in normalized_message
            ):
                return json_response(
                    {
                        'error': message
                    },
                    403
                )

            return json_response(
                {
                    'error': message
                },
                400
            )

        rows = (
            res
            if isinstance(res, list)
            else []
        )

        if not rows:
            return json_response(
                {
                    'error': 'Appointment update returned no result.'
                },
                500
            )

        # The RPC returns the affected appointment row for both cancel and delete.
        return json_response(
            rows[0],
            200
        )

    except Exception as error:
        print(
            'ADMIN ATOMIC APPOINTMENT RELEASE ERROR:',
            error
        )

        return json_response(
            {
                'error': 'Could not update this appointment.'
            },
            500
        )


@data_bp.route('/api/data', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def data_proxy():
    token = get_bearer_token()

    if not token:
        return json_response(
            {
                'error': 'Not authenticated. Please log in.'
            },
            401
        )

    table = request.args.get(
        'table',
        ''
    )

    if table not in ALLOWED_TABLES:
        return json_response(
            {
                'error': f'Unknown or disallowed table: {table}'
            },
            400
        )

    query = []

    row_id = request.args.get(
        'id'
    )

    if row_id is not None:
        query.append(
            'id=eq.' + quote(
                row_id,
                safe=''
            )
        )

    eq = request.args.get(
        'eq'
    )

    if eq and '.' in eq:
        col, val = eq.split(
            '.',
            1
        )

        query.append(
            f'{quote(col, safe="")}=eq.{quote(val, safe="")}'
        )

    order = request.args.get(
        'order'
    )

    if order:
        query.append(
            'order=' + quote(
                order,
                safe='.,'
            )
        )

    limit = request.args.get(
        'limit'
    )

    if limit:
        try:
            query.append(
                'limit=' + str(
                    int(limit)
                )
            )

        except ValueError:
            pass

    path = f'/rest/v1/{table}'

    if query:
        path += (
            '?'
            + '&'.join(query)
        )

    method = request.method

    # Ini nagablock sang generic appointment mutations para indi ma-bypass ang atomic queue endpoints.
    # Android feedback currently uses generic PATCH, gani rating fields lang ang ginapabilin diri.
    if table == 'appointments' and method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if method != 'PATCH':
            return json_response(
                {
                    'error': 'Appointment changes must use the dedicated appointment endpoints.'
                },
                403
            )

        if row_id is None:
            return json_response(
                {
                    'error': 'A specific appointment is required.'
                },
                400
            )

        rating_body = (
            request.get_json(
                silent=True
            )
            or {}
        )

        allowed_rating_fields = {
            'rating',
            'rating_comment',
        }

        requested_fields = set(
            rating_body.keys()
        )

        if (
            not requested_fields
            or not requested_fields.issubset(
                allowed_rating_fields
            )
        ):
            return json_response(
                {
                    'error': 'Generic appointment updates are limited to rating feedback.'
                },
                403
            )

    body = None

    extra_headers = {}

    if method == 'GET':
        pass

    elif method == 'POST':
        body = (
            request.get_json(
                silent=True
            )
            or {}
        )

        extra_headers[
            'Prefer'
        ] = 'return=representation'

    elif method in (
        'PUT',
        'PATCH'
    ):
        body = (
            request.get_json(
                silent=True
            )
            or {}
        )

        extra_headers[
            'Prefer'
        ] = 'return=representation'

        method = 'PATCH'

    elif method == 'DELETE':
        extra_headers[
            'Prefer'
        ] = 'return=representation'

    else:
        return json_response(
            {
                'error': 'Method not allowed'
            },
            405
        )

    status, res = supabase_request(
        method,
        path,
        body,
        token,
        extra_headers
    )

    return json_response(
        res,
        status or 200
    )
