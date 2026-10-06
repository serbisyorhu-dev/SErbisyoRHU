                    waiting_list[0].get('service')
                    or waiting_list[0].get('service_name')
                )

            doctors.append({
                'doctor_id': doctor_id,
                'doctor_name': doctor_name,
                'role': doctor.get('role'),
                'position': (
                    doctor.get('position')
                    or doctor.get('dept')
                ),
                'department': (
                    doctor.get('department')
                    or doctor.get('dept')
                    or doctor.get('specialty')
                    or doctor.get('specialization')
                    or doctor.get('position')
                    or 'Medical Doctor'
                ),
                'prefix': prefix,
                'current_number': current_number,
                'current_service': current_service,
                'next_number': next_number,
                'next_service': next_service,
                'waiting': len(waiting_list),
                'booked_count': len(waiting_list),
                'station': station_name,
                'station_status': station_status_value
            })

        # Ini pirmi naga-return sang doctors array; bisan zero appointments, doctor cards dapat ara gihapon.
        return json_response({
            'date': clinic_today,
            'doctors': doctors
        })

    except Exception as error:
        print('PUBLIC QUEUE STATUS ERROR:', error)

        # Kon may unexpected error sa bag-o nga logic, gamiton gihapon ang original queue_state.
        try:
            status, res = supabase_request(
                'GET',
                '/rest/v1/queue_state?id=eq.1&select=current_number,next_number,waiting,current_patient,current_service'
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
