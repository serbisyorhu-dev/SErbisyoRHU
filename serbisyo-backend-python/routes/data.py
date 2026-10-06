from urllib.parse import quote
from datetime import datetime
from zoneinfo import ZoneInfo
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


# Ini nagapangita sang doctor account bisan ang role label yara sa role, staff_role, job_role, position, ukon department.
def is_doctor_staff(person):
    if not isinstance(person, dict):
        return False

    possible_roles = [
        person.get('role'),
        person.get('staff_role'),
        person.get('job_role'),
        person.get('position'),
        person.get('department'),
        person.get('dept'),
        person.get('specialty'),
        person.get('specialization'),
    ]

    for value in possible_roles:
        normalized = str(value or '').strip().lower()
        if normalized in ('doctor', 'medical doctor'):
            return True

    return False


# Ini nagakuha sang current clinic date sa Pilipinas para indi maapil ang future ukon daan nga bookings sa live TV queue.
def clinic_today_iso():
    try:
        return datetime.now(ZoneInfo('Asia/Manila')).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


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
