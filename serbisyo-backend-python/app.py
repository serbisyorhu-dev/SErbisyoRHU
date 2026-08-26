import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_session import Session

from config import FLASK_SECRET_KEY, ALLOWED_ORIGIN
from routes.auth import auth_bp
from routes.data import data_bp
from routes.chat import chat_bp

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY or 'dev-only-insecure-key-set-FLASK_SECRET_KEY-in-render'

# ------------------------------------------------------------
# Server-side sessions (closest match to how the PHP version worked —
# only a random session ID sits in the browser's cookie; the actual
# Supabase access token stays stored on the server, never sent to
# the browser in readable form).
#
# Filesystem-based: fine for a single Render instance (the free tier
# runs exactly one). If you ever scale to multiple instances, this
# would need to move to Redis so every instance shares the same
# session store — not needed for a thesis-scale deployment.
# ------------------------------------------------------------
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = False

# ------------------------------------------------------------
# CRITICAL for cross-domain auth: your frontend (Vercel) and backend
# (Render) are on different domains. For the session cookie to be
# sent along with cross-origin fetch() calls, it MUST be:
#   - SameSite=None  (allows the cookie cross-site)
#   - Secure=True     (required by browsers whenever SameSite=None —
#                       both Vercel and Render serve over HTTPS, so
#                       this is satisfied automatically)
# Skipping either of these is the #1 reason "it works on localhost
# but login silently fails once deployed" happens with this exact
# frontend/backend split.
# ------------------------------------------------------------
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

Session(app)

# ------------------------------------------------------------
# CORS: only your real Vercel URL should be allowed once deployed.
# supports_credentials=True is required so the browser actually
# sends/receives the session cookie on cross-origin requests —
# without it, fetch(..., {credentials:'include'}) on the frontend
# silently gets no cookie back.
# ------------------------------------------------------------
CORS(
    app,
    supports_credentials=True,
    origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN != '*' else '*',
)

app.register_blueprint(auth_bp)
app.register_blueprint(data_bp)
app.register_blueprint(chat_bp)


@app.route('/')
def index():
    return jsonify({'status': 'SERbisyo RHU backend is running.'})


if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
