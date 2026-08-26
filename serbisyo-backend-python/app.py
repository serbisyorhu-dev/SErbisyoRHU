import os
from flask import Flask, jsonify
from flask_cors import CORS

from config import ALLOWED_ORIGIN
from routes.auth import auth_bp
from routes.data import data_bp
from routes.chat import chat_bp
from routes.upload import upload_bp

app = Flask(__name__)

# ------------------------------------------------------------
# No server-side sessions anymore — auth is token-based (the app
# stores its own access token and sends it as "Authorization: Bearer
# <token>" on every request). This fixes cross-domain login breaking
# on mobile browsers that block third-party cookies (Vercel frontend
# + Render backend are different domains, so cookie-based sessions
# were never reliable there).
# ------------------------------------------------------------

CORS(
    app,
    origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN != '*' else '*',
)

app.register_blueprint(auth_bp)
app.register_blueprint(data_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(upload_bp)


@app.route('/')
def index():
    return jsonify({'status': 'SERbisyo RHU backend is running.'})


if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
