# Splitwise Lite

Splitwise Lite is a mobile-first expense splitter. Friends add shared costs to a
group and the app shows who owes whom, plus the fewest payments needed to settle up.
It is built with FastAPI, SQLite, and a plain HTML/CSS/JavaScript frontend that
installs on a phone as a Progressive Web App (PWA).

## Features

- Sign in with your name and phone number (no password), on any device
- Invite friends to a group with a link; they join by signing in
- Create groups (trips, flatmates, events) with members and a currency symbol
- Add expenses paid by one person and split equally between everyone or a chosen few
- Live balances: who gets money back and who owes
- "Settle up" suggestions using a debt-simplification algorithm
- Record repayments with one tap ("Mark paid")
- "Remind" button shares a payment reminder via the phone's share sheet, or WhatsApp on desktop
- Each person accepts or rejects their own share of a new expense; a rejection
  re-splits the cost between the rest and offers to message the payer
- Activity feed shows who is in each split, with delete, which recalculates balances
- "Tell members" / "Notify members" buttons share a new group or expense with everyone
- Installable on Android and iPhone ("Add to Home Screen"), works full screen

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Pydantic
- PostgreSQL (optional, for hosting)
- HTML, CSS, JavaScript (PWA: web manifest + service worker)

## Setup

Requires Python 3.10 or newer.

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r backend/requirements.txt
```

Start the application:

```bash
uvicorn backend.main:app --reload
```

Open the application:

http://localhost:8000

API documentation:

http://localhost:8000/docs

The SQLite database is created as `splitwise.db` in the project root. Set the `DATABASE_URL` environment variable
to use a different location (see `.env.example`).

### Running tests

```bash
pip install -r backend/requirements-dev.txt
python -m pytest backend/tests
```

Tests use a temporary database and never touch `splitwise.db`.

## Using it on your phone

1. Start the server so your phone can reach it:
   `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
2. On a phone on the same Wi-Fi, open `http://<your-computer-ip>:8000`.
3. Use **Add to Home Screen** (Safari share menu, or Chrome's menu) to install it.

Browsers only allow the offline service worker and the install prompt over HTTPS
(or localhost). For a real install, deploy to any free Python host such as
Render or Railway, which serves the app over HTTPS.

## Deploy online for free (Render + Neon)

Render runs the app for free over HTTPS, so it installs on phones like a real app.
Its free disk is wiped on every restart, so keep the data in a free Neon Postgres
database instead of SQLite.

1. **Database:** sign up at https://neon.tech (free), create a project, and copy the
   connection string from the dashboard (it starts with `postgresql://`).
2. **App:** sign up at https://render.com with your GitHub account.
3. Click **New > Blueprint**, pick the `splitwise-lite` repository and click **Connect**.
   Render reads `render.yaml` from the repo.
4. When asked for `DATABASE_URL`, paste the Neon connection string, then click **Apply**.
5. Wait for the deploy to finish (about 3 minutes) and open the
   `https://splitwise-lite-xxxx.onrender.com` link Render shows.

Free Render apps go to sleep after 15 minutes without visits, so the first visit
after that takes up to a minute to load. Every push to the default branch redeploys.

## Main Endpoints

Every endpoint except sign-in needs the `Authorization: Bearer <token>` header
returned by `/auth/signin`, and you only see groups you are a member of.

```text
POST   /auth/signin                              {name, phone} -> {token, user}
GET    /auth/me
POST   /groups/join/{invite_code}                join via invite link (claims the member with your name)

POST   /groups/                                  {name, currency?, members?}
GET    /groups/
GET    /groups/{group_id}
DELETE /groups/{group_id}

POST   /groups/{group_id}/members                {name}
DELETE /groups/{group_id}/members/{member_id}    (409 if they have expenses or payments)

POST   /groups/{group_id}/expenses               {description, amount, paid_by_id, split_between?}
GET    /groups/{group_id}/expenses
DELETE /groups/{group_id}/expenses/{expense_id}
POST   /groups/{group_id}/expenses/{expense_id}/respond   {decision: accept|reject} for your own share

POST   /groups/{group_id}/settlements            {from_member_id, to_member_id, amount}
GET    /groups/{group_id}/settlements
DELETE /groups/{group_id}/settlements/{settlement_id}

GET    /groups/{group_id}/balances               balances + suggested settle-up payments
```

Amounts are accepted with up to two decimal places and stored as integer cents
(paise), so splitting never suffers from floating-point rounding. When an amount
does not divide evenly, the leftover cents go one each to the first members
(100 split 3 ways is 33.34, 33.33, 33.33).

The algorithm implementations are in:

backend/algorithms.py

## Complexity

- **Equal split:** O(k) time for k members sharing an expense.
- **Balances:** O(E + S) time, one pass over every expense share and settlement.
- **Debt simplification:** O(n log n) time to sort debtors and creditors, then a
  linear two-pointer pass. Each payment fully clears at least one person, so it
  produces at most n - 1 payments.

## Project Structure

```text
splitwise-lite/
├── backend/
│   ├── algorithms.py
│   ├── crud.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── schemas.py
│   └── tests/
├── frontend/
│   ├── icons/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.webmanifest
│   └── service-worker.js
├── render.yaml
├── .env.example
├── .gitignore
└── README.md
```

## Limitations

Sign-in has no password or SMS code: anyone who knows your phone number can sign
in as you. That is fine for friends splitting bills, but it is not real security.
Notifications are sent by sharing a message (share sheet or WhatsApp) rather than
as push notifications.

## Security

No API keys or secrets are committed to the repository. The app needs no
external services to run.
