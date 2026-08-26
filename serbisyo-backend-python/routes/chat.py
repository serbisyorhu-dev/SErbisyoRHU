import requests
from flask import Blueprint, request, session, jsonify

from config import GEMINI_API_KEY

chat_bp = Blueprint('chat', __name__)

SYSTEM_INSTRUCTION = (
    "Ikaw si Enrique, ang mabuot kag mapinabuligon nga AI health assistant sang SERbisyo RHU System "
    "sa San Enrique, Iloilo, Pilipinas. Magsabat ka PERMI sa Hiligaynon/Ilonggo nga lengguahe, "
    "mahigalaon, simple, kag mahilway maghambal. Ang imo trabaho amo ang magbulig sa mga pasyente "
    "parte sa: (1) pag-book sang appointment sa RHU, (2) pag-check sang ila live queue number, kag "
    "(3) kinatibuk-an nga impormasyon parte sa mga serbisyo sang RHU. Indi ka gid maghatag sang "
    "medical diagnosis, indi ka magrekomenda sang bulong — sa baylo, pasabton nga dapat magpakita "
    "sila personal sa doktor para sa seryoso nga mga kabalaka."
)


def json_response(data, status=200):
    return jsonify(data), status


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    if not session.get('access_token'):
        return json_response({'error': 'Not authenticated. Please log in.'}, 401)

    if not GEMINI_API_KEY:
        return json_response({'error': 'The chatbot is not configured yet. Set GEMINI_API_KEY as an environment variable in Render.'}, 500)

    body = request.get_json(silent=True) or {}
    message = (body.get('message') or '').strip()
    if not message:
        return json_response({'error': 'Message is required.'}, 400)

    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    payload = {
        'system_instruction': {'parts': [{'text': SYSTEM_INSTRUCTION}]},
        'contents': [{'role': 'user', 'parts': [{'text': message}]}],
        'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 400},
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
    except requests.RequestException as e:
        return json_response({'error': f'Could not reach Gemini: {e}'}, 502)

    try:
        result = resp.json()
    except ValueError:
        result = {}

    if resp.status_code >= 400:
        msg = (result.get('error') or {}).get('message', 'Gemini request failed.')
        return json_response({'error': msg}, 500)

    try:
        reply = result['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError):
        finish_reason = (result.get('candidates') or [{}])[0].get('finishReason', 'unknown')
        return json_response({'error': f"Enrique couldn't answer that one (reason: {finish_reason}). Try rephrasing."}, 500)

    return json_response({'reply': reply.strip()})
