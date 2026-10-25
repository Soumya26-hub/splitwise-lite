# Splitwise Lite

Splitwise Lite is a mobile-first expense splitter. Friends add shared costs to a
group and the app shows who owes whom, plus the fewest payments needed to settle up.
It is built with FastAPI, SQLite, and a plain HTML/CSS/JavaScript frontend that
installs on a phone as a Progressive Web App (PWA).

## Features

- Sign in with your name and phone number (no password), on any device
- Invite friends to a group with a link, or add people who have signed in by
  searching their name (made-up names cannot be added)
- Create groups (trips, flatmates, events) with members and a currency symbol
- Add expenses paid by one person and split equally between everyone or a chosen few
- Live balances: who gets money back and who owes
- "Settle up" suggestions using a debt-simplification algorithm
- Record repayments with one tap ("Mark paid"); the payment only clears the debt
  once the person paid taps "Received" ("Not received" removes it)
- "Remind" opens the member's own WhatsApp chat with the reminder filled in (falls back to the share sheet if they have not signed in)
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
- Docker
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

### Running with Docker

```bash
docker build -t splitwise-lite .
docker run -p 8000:8000 splitwise-lite
```

Open `http://localhost:8000` for the app and `http://localhost:8000/docs` for the Swagger API docs.
Data is kept in SQLite inside the container; pass `-e DATABASE_URL=...` to use Postgres instead.

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
GET    /users/search?q=<name>                    signed-in people (id and name only)
                                                 (group responses include members' phone numbers, visible to fellow members only)
POST   /groups/join/{invite_code}                join via invite link (claims the member with your name)

POST   /groups/                                  {name, currency?, members?}
GET    /groups/
GET    /groups/{group_id}
DELETE /groups/{group_id}

POST   /groups/{group_id}/members                {user_id}
DELETE /groups/{group_id}/members/{member_id}    (409 if they have expenses or payments)

POST   /groups/{group_id}/expenses               {description, amount, paid_by_id, split_between?}
GET    /groups/{group_id}/expenses
DELETE /groups/{group_id}/expenses/{expense_id}
POST   /groups/{group_id}/expenses/{expense_id}/respond   {decision: accept|reject} for your own share

POST   /groups/{group_id}/settlements            {from_member_id, to_member_id, amount}
GET    /groups/{group_id}/settlements
POST   /groups/{group_id}/settlements/{settlement_id}/confirm   the person paid confirms receipt
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

## Architecture

The backend is split into layers, each in its own module:

- `main.py`: HTTP routes. Each route checks who is signed in, calls one function and returns the result.
- `schemas.py`: Pydantic request and response models, including input validation.
- `services.py`: business rules (who can confirm a payment, who can reject a share, which members can be removed).
  Broken rules raise `NotFound`, `Forbidden`, `Conflict` or `InvalidRequest`, which `main.py` turns into 404/403/409/422 responses.
- `crud.py`: database reads and writes through SQLAlchemy.
- `models.py`: SQLAlchemy tables (users, groups, members, expenses, expense shares, settlements).
- `algorithms.py`: pure functions for splitting, balances and debt simplification, with no database access.

Database details:

- Foreign keys used for lookups (`members.group_id`, `expenses.group_id`, `expense_shares.expense_id`,
  `settlements.group_id`) are indexed, along with the unique `phone`, `token` and `invite_code` columns.
- The expense list loads all shares in one extra query (`selectinload`) instead of one query per expense.
  `test_queries_and_logging.py` checks that the number of queries stays the same as expenses are added.
- Each write commits once, so an expense and its shares, or a re-split after a rejection, are saved together or not at all.

Logging: every request is logged with its method, path, status code and duration. Broken business rules are
logged as warnings and unexpected errors with a full traceback.

GitHub Actions (`.github/workflows/tests.yml`) runs the tests on every push and pull request, and also builds
the Docker image and checks that the container answers.

## Project Structure

```text
splitwise-lite/
├── .github/workflows/tests.yml
├── backend/
│   ├── algorithms.py
│   ├── crud.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── schemas.py
│   ├── services.py
│   └── tests/
├── frontend/
│   ├── icons/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.webmanifest
│   └── service-worker.js
├── Dockerfile
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
