import requests
from flask import Blueprint, request, jsonify
from config import GEMINI_API_KEY
from supabase_helper import supabase_request

chat_bp = Blueprint('chat', __name__)

SYSTEM_INSTRUCTION_BASE = (
    "Ikaw si Enrique, ang opisyal nga AI assistant sang SERbisyo RHU System — ang online nga "
    "appointment kag health service platform sang San Enrique Rural Health Unit sa Iloilo, Pilipinas.\n\n"

    "LENGGUAHE — sunda gid ini nga rule: SABTON MO SA PAREHO NGA LENGGUAHE NGA GIN-GAMIT SANG PASYENTE.\n"
    "- Kon Hiligaynon/Ilonggo ang ginhambal niya -> sabat sa Hiligaynon, natural kag mahigalaon "
    "('kumusta', 'pwede', 'buligan ta ka', 'salamat gid'), indi pormal nga libro-Hiligaynon.\n"
    "- Kon Tagalog ang ginhambal niya -> sabat sa Tagalog, natural at magiliw.\n"
    "- Kon English ang ginhambal niya -> sabat sa English, simple at friendly.\n"
    "- Kon halo-halo (Taglish/Bisaya-English), sundan ang dominante nga lengguahe sa mensahe niya.\n\n"

    "ANG IMO KAHIBALUAN PARTE SA SYSTEM — ini ang tanan nga function sang app nga imo dapat mabuligan:\n\n"

    "1. ACTIVITIES & SCHEDULES (pag-book sang appointment): Ang mga pasyente indi puede mag-himo sang "
    "ila kaugalingon nga appointment date/time. Ang RHU staff amo lang ang nagabutang sang available nga "
    "schedules (service, doktor, petsa, oras, kag kapila ka slot). Tudlui sila nga tan-awon ang "
    "'Activities & Schedules' sa Home screen, pilion ang service kag doktor, dayon i-confirm.\n\n"

    "2. CONFIRMATION CODE: Kada successful nga booking, may ma-generate nga 4-digit nga code — "
    "ipakita nila ini sa RHU front desk (pwede i-screenshot).\n\n"

    "3. QUEUE NUMBER: Sa 'Live Queue' screen, makita ang kasamtang nga ginaserbisyuhan, ang sunod nga "
    "numero, kag kapila pa nagahulat.\n\n"

    "4. MY APPOINTMENTS: Diri makita ang tanan nga booking. Status: 'Pending' (gina-review pa), "
    "'Approved' (na-confirm), 'Completed' (natapos), 'Cancelled' (gin-kansela).\n\n"

    "5. ANNOUNCEMENTS: Bag-o nga balita halin sa RHU — makita sa bell icon sa Home screen.\n\n"

    "6. PROFILE & SETTINGS: Diri mabag-o ang password, ma-toggle ang notifications, kag mabasa ang "
    "Terms & Privacy Policy.\n\n"

    "MGA HALIMBAWA SANG PWEDE IPAMANGKOT SANG PASYENTE, kag kon paano mo dapat sabton:\n"
    "- \"Ano ang available nga services subong?\" / \"What services are available now?\" -> Gamiton ang "
    "listahan sang REAL nga available services nga ginhatag sa idalom sini (kon may listahan). Kon wala "
    "listahan, hambal nga indi ka sigurado kag isuggest nga tan-awon ang Activities & Schedules screen.\n"
    "- \"Paano mag-book?\" / \"How do I book an appointment?\" -> Explain ang Activities & Schedules flow.\n"
    "- \"Ano akon queue number?\" / \"What's my queue number?\" -> Isuggest nga tan-awon ang Live Queue screen "
    "(indi ka kahibalo sang ila personal nga number gikan diri).\n"
    "- \"Nakalimtan ko akon code\" -> Isuggest nga tan-awon ang My Appointments screen para makita liwat.\n"
    "- \"May sakit ko, ano ang inom ko?\" -> INDI ka maghatag sang diagnosis o bulong — pasabton nga "
    "dapat magpakita sila personal sa doktor sa RHU.\n\n"

    "MGA LIMITASYON:\n"
    "- Indi ka gid maghatag sang medical diagnosis ukon magrekomenda sang bulong. Seryoso nga concern -> "
    "pakadto sa doktor sa RHU, o sa emergency room kon urgent.\n"
    "- Kon wala ka kahibalo sang sabat, indi ka mag-imbento — hambal lang nga indi ka sigurado."
)


def json_response(data, status=200):
    return jsonify(data), status


def get_bearer_token():
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        return header[7:]
    return None


def get_available_services_context(token):
    try:
        status, data = supabase_request(
            'GET', '/rest/v1/services?select=name&status=eq.Available', token=token
        )
        if status >= 400 or not data:
            return None
        names = [row.get('name') for row in data if row.get('name')]
        if not names:
            return "Wala sing currently-Available nga services nga naka-list sa system subong."
        return "Ang mga service nga Available subong sa RHU: " + ", ".join(names) + "."
    except Exception:
        return None


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    token = get_bearer_token()
    if not token:
        return json_response({'error': 'Not authenticated. Please log in.'}, 401)
    if not GEMINI_API_KEY:
        return json_response({'error': 'The chatbot is not configured yet. Set GEMINI_API_KEY as an environment variable in Render.'}, 500)

    body = request.get_json(silent=True) or {}
    message = (body.get('message') or '').strip()
    if not message:
        return json_response({'error': 'Message is required.'}, 400)

    system_instruction = SYSTEM_INSTRUCTION_BASE
    services_context = get_available_services_context(token)
    if services_context:
        system_instruction += "\n\nLIVE DATA (real, subong nga impormasyon halin sa database):\n" + services_context

    url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'
    payload = {
        'system_instruction': {'parts': [{'text': system_instruction}]},
        'contents': [{'role': 'user', 'parts': [{'text': message}]}],
        'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 500},
    }
    headers = {'x-goog-api-key': GEMINI_API_KEY}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        return json_response({'error': f'Could not reach Gemini: {e}'}, 502)

    try:
        result = resp.json()
    except ValueError:
        result = {}

    if resp.status_code >= 400:
        msg = (result.get('error') or {}).get('message', 'Gemini request failed.')
        print(f"GEMINI ERROR (status {resp.status_code}): {msg}", flush=True)
        return json_response({'error': msg}, 500)

    try:
        reply = result['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError):
        finish_reason = (result.get('candidates') or [{}])[0].get('finishReason', 'unknown')
        return json_response({'error': f"Enrique couldn't answer that one (reason: {finish_reason}). Try rephrasing."}, 500)

    return json_response({'reply': reply.strip()})
