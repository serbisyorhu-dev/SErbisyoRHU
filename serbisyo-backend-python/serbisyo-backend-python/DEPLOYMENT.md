# SERbisyo RHU — Deploying with GitHub + Render + Vercel

Two separate deployments now: **backend** (Python/Flask) on Render,
**frontend** (static HTML) on Vercel. They talk to each other over the
open internet, not through XAMPP anymore.

## Why this needed more than a language port

Once your frontend and backend live on *different domains*, browsers treat
every request between them as cross-origin. Two things had to change
correctly, or login would silently fail after deploying even though it
worked fine locally:

1. **CORS** — the backend must explicitly allow your Vercel domain (`app.py`, via `ALLOWED_ORIGIN`)
2. **Cookies** — the session cookie needs `SameSite=None; Secure` to survive a cross-origin request (already set in `app.py`)

Both are already wired up — you just need to set one environment variable correctly (Part C below).

## Part A — Push to GitHub

1. Create a new GitHub repo (public or private, either works).
2. Put **both** folders in it — `serbisyo-backend-python/` and your existing frontend files (`index.html`, `reset-password.html`, `assets/`) — a monorepo with two subfolders is completely fine; both Render and Vercel let you point at a specific subfolder as the project root.
3. Push everything **except** `.env` (already excluded via `.gitignore` — never commit real secrets).

## Part B — Deploy the backend to Render

1. render.com → **New → Web Service** → connect your GitHub repo
2. **Root Directory:** `serbisyo-backend-python` (if monorepo)
3. **Runtime:** Python 3
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `gunicorn app:app`
6. **Environment** tab → add these one by one (real values, from `.env.example`'s list):
   ```
   SUPABASE_URL
   SUPABASE_ANON_KEY
   GEMINI_API_KEY
   ADMIN_INVITE_CODE
   FLASK_SECRET_KEY
   ALLOWED_ORIGIN        (leave blank for now — comes back in Part D)
   ```
7. Deploy. Once live, you'll get a URL like `https://serbisyo-backend.onrender.com`. Visit it directly — you should see `{"status": "SERbisyo RHU backend is running."}`.

**Free tier note:** Render's free web services sleep after inactivity — the first request after idle time takes a few extra seconds to wake up. Normal, not a bug.

## Part C — Deploy the frontend to Vercel

1. vercel.com → **New Project** → same GitHub repo
2. **Root Directory:** the folder containing `index.html` (if monorepo, point at that subfolder; if it's the whole repo root, leave default)
3. **Framework Preset:** "Other" (it's plain static HTML, no build step needed)
4. Deploy. You'll get a URL like `https://serbisyo-rhu.vercel.app`.

## Part D — Connect them to each other

Two edits, then redeploy both:

1. **In `index.html`** (and `reset-password.html`), find:
   ```js
   const BACKEND_URL = 'http://localhost:5000';
   ```
   Change it to your real Render URL:
   ```js
   const BACKEND_URL = 'https://serbisyo-backend.onrender.com';
   ```
   Commit and push — Vercel auto-redeploys on every push.

2. **Back in Render**, edit the `ALLOWED_ORIGIN` environment variable to your real Vercel URL:
   ```
   ALLOWED_ORIGIN=https://serbisyo-rhu.vercel.app
   ```
   Save — Render redeploys automatically.

## Part E — Also update Supabase's redirect URL allowlist

Same requirement as before, just with your new real domain instead of localhost:
Supabase → Authentication → URL Configuration → Redirect URLs → add:
```
https://serbisyo-rhu.vercel.app/reset-password.html
```

## Part F — Test it end to end

1. Open your Vercel URL.
2. Log in with your admin account.
3. Open browser DevTools → Network tab → confirm requests are going to your Render URL and coming back with `200`, not CORS errors in the console.
4. If you see a CORS error mentioning "No Access-Control-Allow-Origin" — `ALLOWED_ORIGIN` on Render doesn't exactly match your Vercel URL (check for a trailing slash mismatch, that's the most common cause).
5. If login succeeds but every subsequent request comes back 401 "Not authenticated" — the session cookie isn't being sent; double check `credentials: 'include'` is present in the fetch calls (it already is in the code provided) and that both URLs are HTTPS (Render and Vercel both give you HTTPS automatically).

## Local testing before deploying (optional but recommended)

You can run the whole thing locally first to catch bugs before pushing:

```bash
cd serbisyo-backend-python
pip install -r requirements.txt
cp .env.example .env      # then fill in real values in .env
python app.py              # starts on http://localhost:5000
```

Leave `BACKEND_URL` in `index.html` as `http://localhost:5000`, open `index.html` directly or via any local static server, and test the whole flow before touching Render/Vercel at all.
