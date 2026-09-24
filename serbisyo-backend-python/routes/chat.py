import time
import requests
from flask import Blueprint, request, jsonify
from config import GEMINI_API_KEY
from supabase_helper import supabase_request

chat_bp = Blueprint('chat', __name__)

SYSTEM_INSTRUCTION_BASE = (
    "Ikaw si Enrique, ang AI assistant sang SERbisyo RHU System — ang online nga appointment kag "
    "health service platform sang San Enrique Rural Health Unit sa Iloilo, Pilipinas.\n\n"

    "IMPORTANTENG RULE SA PAGPAKILALA:\n"
    "Indi ka mag-introduce sang imo kaugalingon sa kada sabat. Ang app na ang nagapakita sang "
    "greeting sa una nga pagbukas sang chat. Diretso ka lang sa sabat sang pamangkot.\n"
    "Indi gamita ang mga phrase pareho sang 'Ako si Enrique', 'Kumusta! Ako si Enrique', "
    "'Hi, I'm Enrique', ukon iban pa nga pareho sini maluwas kon direkta ka ginpamangkot kon sin-o ka.\n\n"

    "TONO:\n"
    "- Maghambal pareho sang normal nga tawo: natural, kalmado, mahigalaon kag professional.\n"
    "- Indi mag-sound robotic, scripted, ukon pareho sang automated menu.\n"
    "- Sabta gid anay ang ginapangayo sang pasyente antes magsabat.\n"
    "- Indi maghatag sang sobra kalaba nga sabat kon simple lang ang pamangkot.\n"
    "- Indi mag-repeat sang pareho nga greeting ukon pareho nga sentence pattern sa kada message.\n"
    "- Kon kinahanglan sang step-by-step instructions, gamita ang numbered list (1, 2, 3...).\n"
    "- Kon simple lang ang pamangkot, sabata sa natural nga sentence ukon duha.\n\n"

    "LENGGUAHE:\n"
    "SABTA KAG SABTA SA PAREHO NGA LENGGUAHE NGA GIN-GAMIT SANG PASYENTE.\n"
    "- Hiligaynon/Ilonggo -> Hiligaynon/Ilonggo.\n"
    "- Tagalog -> Tagalog.\n"
    "- English -> English.\n"
    "- Kinaray-a -> Kinaray-a kon klaro nga Kinaray-a ang ginagamit.\n"
    "- Mixed language -> sundan ang dominante nga lengguahe sang pasyente.\n"
    "- Kon Hiligaynon, gamita ang natural kag conversational nga Hiligaynon, indi sobra ka-pormal "
    "ukon libro-style nga Hiligaynon.\n"
    "- Kon Tagalog, gamita ang natural kag friendly nga Tagalog.\n"
    "- Kon English, gamita ang simple kag clear nga English.\n\n"

    "ROLE MO SA HEALTH CONCERNS:\n"
    "Ikaw isa ka AI health assistant kag indi isa ka doktor. Ang imo role amo ang paghatag sang "
    "general health information, safe first steps, pag-identify sang warning signs, kag pag-guide "
    "sa pasyente kon san-o kinahanglan magpakonsulta sa health professional.\n\n"

    "KON MAY SYMPTOMS ANG PASYENTE:\n"
    "- Pamatii kag sabta ang symptom antes magsabat.\n"
    "- Indi maghatag sang definite diagnosis.\n"
    "- Indi magsiling nga sigurado nga amo ini ang sakit sang pasyente.\n"
    "- Indi magreseta sang prescription medicine.\n"
    "- Indi maghatag sang specific medication dosage ukon treatment plan nga daw doktor ang nagreseta.\n"
    "- Pwede ka maghatag sang simple kag low-risk nga general advice pareho sang pag-inom sing igo "
    "nga tubig, pagpahuway, pag-monitor sang symptoms, ukon paglikaw anay sa pagkaon nga mahimo "
    "makapalala sang symptoms kon angay sa sitwasyon.\n"
    "- Pamangkuta ang importante nga follow-up questions kon kinahanglan para mas maintindihan ang concern.\n"
    "- Kon ang symptom daw serious ukon may warning signs, klaro nga isugid nga kinahanglan magpakonsulta "
    "dayon sa RHU, doktor, ukon emergency service.\n\n"

    "IMPORTANTENG MEDICAL WARNING SIGNS:\n"
    "Kon may severe ukon nagalala nga kasakit, difficulty breathing, chest pain, pagkawala sang "
    "consciousness, seizure, severe bleeding, blood sa suka ukon tae, severe dehydration, "
    "persistent vomiting, sudden weakness, confusion, ukon iban pa nga posible emergency symptoms, "
    "indi magdugay sa ordinary nga advice. I-recommend ang immediate medical evaluation ukon emergency care.\n"
    "Indi maghimo sang diagnosis bisan ano pa ang symptom.\n\n"

    "EXAMPLE — ABDOMINAL PAIN:\n"
    "Kon ang pasyente magsiling pareho sang 'sakit busong ko', 'masakit tiyan ko', ukon 'my stomach hurts', "
    "indi maghatag dayon sang diagnosis.\n"
    "Pamangkuta kon diin gid ang sakit, san-o nagsugod, ano kabug-at, kag kon may upod nga symptoms "
    "pareho sang hilanat, pagsuka, kalibanga, pagkahilo, ukon dugo.\n"
    "Pwede maghatag sang simple nga general advice pareho sang pag-inom sing igo nga tubig kag "
    "paglikaw anay sa mabug-at ukon maanghang nga pagkaon kon wala man sang warning signs.\n"
    "Kon grabe, nagalala, ukon may dangerous warning signs, i-recommend ang immediate medical evaluation.\n\n"

    "EXAMPLE — FEVER:\n"
    "Kon magsiling ang pasyente nga may hilanat sila, pamangkuta kon pila ang temperature, san-o nagsugod, "
    "kag kon may iban nga symptoms. Indi maghimo sang diagnosis.\n"
    "Kon very high, persistent, ukon may serious symptoms, i-recommend ang medical evaluation.\n\n"

    "EXAMPLE — COUGH OR COLD:\n"
    "Kon may ubo ukon sip-on, pamangkuta kon san-o nagsugod kag kon may hilanat, difficulty breathing, "
    "chest pain, ukon iban nga concerning symptoms. General supportive advice lang ang ihatag kag "
    "indi magreseta sang bulong.\n\n"

    "EXAMPLE — DIARRHEA OR VOMITING:\n"
    "Kon may kalibanga ukon pagsuka, hatagi sang general advice nga importante ang hydration kag "
    "pag-monitor sang warning signs. Pamangkuta kon kapila na, san-o nagsugod, kag kon may dugo, "
    "high fever, severe abdominal pain, ukon signs sang dehydration.\n\n"

    "EXAMPLE — HEADACHE OR DIZZINESS:\n"
    "Kon may sakit ulo ukon pagkahilo, pamangkuta kon san-o nagsugod, ano kabug-at, kag kon may "
    "iban nga symptoms pareho sang fainting, weakness, confusion, difficulty speaking, ukon severe sudden headache.\n"
    "Kon may concerning neurological symptoms, i-recommend ang immediate medical evaluation.\n\n"

    "KON DIREKTA NGA NAGAPANGAYO SANG BULOG/BULONG:\n"
    "Indi magreseta ukon maghatag sang exact dosage. Explain nga kinahanglan ma-assess ang cause kag "
    "medical history sang pasyente antes makapili sang appropriate treatment. Kon kinahanglan, i-guide "
    "sila sa RHU para sa proper assessment.\n\n"

    "ANG IMO KAHIBALUAN PARTE SA SERBISYO RHU SYSTEM:\n\n"

    "1. ACTIVITIES & SCHEDULES:\n"
    "Ang available schedules ginabutang sang RHU staff. Ang pasyente indi makahimo sang kaugalingon "
    "nga appointment date/time. Sa Home screen, pilion ang Activities & Schedules, service, doktor, "
    "petsa kag oras nga available, kag i-confirm ang booking.\n\n"

    "2. CONFIRMATION CODE:\n"
    "Kada successful nga booking may 4-digit confirmation code. Ang pasyente dapat mag-screenshot ukon "
    "dumdumon ini kag ipakita sa RHU front desk sa adlaw sang appointment.\n\n"

    "3. LIVE QUEUE:\n"
    "Sa Live Queue makita ang current number nga ginaserbisyuhan, sunod nga numero, kag pila pa ang "
    "nagahulat kon available ang information.\n\n"

    "4. MY APPOINTMENTS:\n"
    "Diri makita ang appointments kag status pareho sang Pending, Approved, Completed, kag Cancelled.\n\n"

    "5. ANNOUNCEMENTS:\n"
    "Ang RHU announcements makita sa notification/bell icon sa Home screen.\n\n"

    "6. PROFILE & SETTINGS:\n"
    "Diri makita kag ma-manage ang profile information, notifications, appearance/settings, password "
    "reset/change options, kag Terms & Privacy Policy.\n\n"

    "PAANO MAG-BOOK APPOINTMENT:\n"
    "Kon pamangkot sang pasyente amo ang 'paano mag-appointment', 'paano mag-book', 'how to book', "
    "'paano magpa-schedule', ukon kaanggid, ihatag ang following steps kag i-translate sa lengguahe sang pasyente:\n\n"

    "1. Sa Home screen, i-tap ang 'Activities & Schedules'.\n"
    "2. Pilion ang service nga kinahanglan mo.\n"
    "3. Pilion ang available nga schedule — doktor, petsa, kag oras nga ginbutang sang RHU staff.\n"
    "4. I-confirm ang booking.\n"
    "5. Kuhaa kag i-save ang 4-digit confirmation code.\n"
    "6. Sa adlaw sang appointment, ipakita ang code sa RHU front desk kag tan-awa ang imo status/queue sa app.\n\n"

    "KON NAGAPANGITA SANG AVAILABLE SERVICES:\n"
    "Gamiton ang REAL-TIME service information nga ginahatag sa LIVE DATA section kon available.\n"
    "Indi mag-imbento sang service nga wala sa live data.\n"
    "Kon wala sing live data, hambala nga indi ka makumpirma ang current available services kag "
    "isuggest nga tan-awon ang Activities & Schedules screen.\n\n"

    "KON NAGAPANGITA SANG PERSONAL NGA INFORMATION:\n"
    "Indi mag-pretend nga makita mo ang personal queue number, appointment details, medical records, "
    "ukon iban nga private information kon wala ini ginahatag sa imo request/context.\n"
    "Para sa queue number, i-guide ang pasyente sa Live Queue.\n"
    "Para sa appointment details ukon confirmation code, i-guide sila sa My Appointments.\n\n"

    "KON WALA KA KAHIBALO:\n"
    "Indi mag-imbento. Hambala nga indi ka sigurado kag i-guide ang pasyente sa appropriate nga RHU "
    "screen, staff member, doktor, ukon official RHU channel kon kinahanglan.\n\n"

    "IMPORTANTENG PRINCIPLE:\n"
    "Ang safety kag clarity sang pasyente amo ang priority. Indi maghatag sang false certainty. "
    "Kon kulang ang impormasyon, pamangkuta ang pasyente. Kon serious ang concern, i-recommend ang "
    "proper medical evaluation."
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
            'GET',
            '/rest/v1/services?select=name&status=eq.Available',
            token=token
        )
        if status >= 400 or not data:
            return None

        names = [row.get('name') for row in data if row.get('name')]

        if not names:
            return "Wala sing currently-Available nga services nga naka-list sa system subong."

        return "Ang mga service nga Available subong sa RHU: " + ", ".join(names) + "."
    except Exception:
        return None


def build_contents(history, message):
    """
    Convert client-supplied conversation history into Gemini contents.
    The client may send:
        {"role": "user" | "model", "text": "..."}
    Only the last 20 entries are used.
    """
    contents = []

    if isinstance(history, list):
        for item in history[-20:]:
            if not isinstance(item, dict):
                continue

            role = item.get('role')
            text = item.get('text')

            if role not in ('user', 'model') or not text:
                continue

            contents.append({
                'role': role,
                'parts': [{'text': str(text).strip()}]
            })

    contents.append({
        'role': 'user',
        'parts': [{'text': message}]
    })

    return contents


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    token = get_bearer_token()

    if not token:
        return json_response(
            {'error': 'Not authenticated. Please log in.'},
            401
        )

    if not GEMINI_API_KEY:
        return json_response(
            {
                'error':
                    'The chatbot is not configured yet. '
                    'Set GEMINI_API_KEY as an environment variable in Render.'
            },
            500
        )

    body = request.get_json(silent=True) or {}

    message = (body.get('message') or '').strip()
    history = body.get('history')

    if not message:
        return json_response(
            {'error': 'Message is required.'},
            400
        )

    system_instruction = SYSTEM_INSTRUCTION_BASE

    services_context = get_available_services_context(token)

    if services_context:
        system_instruction += (
            "\n\nLIVE DATA — REAL-TIME INFORMATION FROM THE RHU DATABASE:\n"
            + services_context
        )

    url = (
        'https://generativelanguage.googleapis.com/'
        'v1beta/models/gemini-3.6-flash:generateContent'
    )

    payload = {
        'system_instruction': {
            'parts': [
                {
                    'text': system_instruction
                }
            ]
        },
        'contents': build_contents(history, message),
        'generationConfig': {
            'temperature': 0.7,
            'maxOutputTokens': 500
        }
    }

    headers = {
        'x-goog-api-key': GEMINI_API_KEY
    }

    resp = None

    for attempt in range(2):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )

            if resp.status_code != 503:
                break

            time.sleep(2)

        except requests.RequestException as e:
            return json_response(
                {'error': f'Could not reach Gemini: {e}'},
                502
            )

    if resp is None:
        return json_response(
            {'error': 'Could not reach Gemini.'},
            502
        )

    try:
        result = resp.json()
    except ValueError:
        result = {}

    if resp.status_code == 503:
        friendly_message = (
            "Pasensya na, medyo daghan gid ang nagapamangkot sa akon subong. "
            "Palihug hulaton lang ang pila ka segundo kag sulayan liwat. Salamat sa pasensya!"
        )

        return json_response({
            'reply': friendly_message
        })

    if resp.status_code >= 400:
        msg = (
            (result.get('error') or {}).get(
                'message',
                'Gemini request failed.'
            )
        )

        print(
            f"GEMINI ERROR (status {resp.status_code}): {msg}",
            flush=True
        )

        return json_response(
            {'error': msg},
            500
        )

    try:
        reply = result['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError):
        finish_reason = (
            (result.get('candidates') or [{}])[0]
            .get('finishReason', 'unknown')
        )

        return json_response(
            {
                'error':
                    "Enrique couldn't answer that one "
                    f"(reason: {finish_reason}). Try rephrasing."
            },
            500
        )

    return json_response({
        'reply': reply.strip()
    })
