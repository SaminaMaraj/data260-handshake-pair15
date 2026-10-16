# Week 2 authentication verification

Login returns an HS256 bearer JWT with a user ID, role, and 30-minute expiry.
Protected requests validate the signature/expiry, then load the active user and
role from MySQL. A frontend role value cannot grant backend access.
The frontend keeps the token in memory, verifies the appropriate dashboard
endpoint, and clears it on logout/reload. Logout does not revoke a copied token;
it expires after 30 minutes.

## Access rules

- Public: `/`, `/health/db`, registration, login.
- Authenticated, either role: `/users/me` and existing student/company/job GET routes.
- Student only: `/students/me/dashboard`, POST `/students`.
- Company only: `/companies/me/dashboard`, POST `/companies`, POST `/jobs`.
- Profile/job creation must use the authenticated user's ID.
- Missing, invalid, expired, or inactive-user tokens: 401.
- Wrong role or another user's ID: 403.

## Run manually

Use your existing Python environment (Python 3.10+ with requirements installed).
The commands below use the interpreter verified on this machine.

Terminal 1, only if the backend is not already running:

```sh
cd ~/Desktop/Lab1/data260-handshake-pair15-main
/Users/bhavana/Desktop/Anaconda3/anaconda3/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 9150 --reload
```

Terminal 2, only if Vite is not already running:

```sh
cd ~/Desktop/Lab1/data260-handshake-pair15-main/frontend
npm run dev -- --port 5174 --strictPort
```

Verification:

```sh
cd ~/Desktop/Lab1/data260-handshake-pair15-main
python3 backend/tests/week2_smoke.py
PYTHONPATH=backend /Users/bhavana/Desktop/Anaconda3/anaconda3/bin/python backend/test_db.py
curl http://127.0.0.1:9150/health/db
curl -i http://127.0.0.1:9150/users/me
cd frontend
npm run build
npm run lint
```

The smoke test creates fresh student/company accounts, profiles, and a job in
MySQL each run. It never deletes existing data and does not print passwords or
tokens. It tests registration/login, role restrictions, ownership, existing
routes, missing/malformed/tampered tokens, duplicate profiles, and CORS.

Open http://localhost:5174. Sign up with a unique email and Student account type,
log in, confirm Student Dashboard and its four cards, then log out. Repeat with
Company and confirm Company Profile, Post a Job, My Job Posts, Applicants, and
Logout. Dashboard action buttons remain Week 2 placeholders.

The local ignored `.env` has a generated `JWT_SECRET_KEY`. Never commit it.
For another checkout, set that variable to a random value of at least 32
characters before starting the backend. `.env.example` intentionally has no
usable secret. Existing ports, database schema, Docker database, and password
hashing are unchanged.
