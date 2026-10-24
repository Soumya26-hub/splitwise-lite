# Splitwise Lite

Splitwise Lite is a mobile-first expense splitter. Friends add shared costs to a
group and the app shows who owes whom, plus the fewest payments needed to settle up.
It is built with FastAPI, SQLite, and a plain HTML/CSS/JavaScript frontend that
installs on a phone as a Progressive Web App (PWA).

## Features

- Create groups (trips, flatmates, events) with members and a currency symbol
- Add expenses paid by one person and split equally between everyone or a chosen few
- Live balances: who gets money back and who owes
- "Settle up" suggestions using a debt-simplification algorithm
- Record repayments with one tap ("Mark paid")
- "Remind" button shares a payment reminder via the phone's share sheet, or WhatsApp on desktop
- Activity feed with delete, which recalculates balances
- Installable on Android and iPhone ("Add to Home Screen"), works full screen

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Pydantic
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

The SQLite database is created as `splitwise.db` in the project root and is
seeded with a demo "Goa Trip" group. Set the `DATABASE_URL` environment variable
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

## Main Endpoints

```text
POST   /groups/                                  {name, currency?, members?}
GET    /groups/
GET    /groups/{group_id}
DELETE /groups/{group_id}

POST   /groups/{group_id}/members                {name}
DELETE /groups/{group_id}/members/{member_id}    (409 if they have expenses or payments)

POST   /groups/{group_id}/expenses               {description, amount, paid_by_id, split_between?}
GET    /groups/{group_id}/expenses
DELETE /groups/{group_id}/expenses/{expense_id}

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
│   ├── seed_data.py
│   └── tests/
├── frontend/
│   ├── icons/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.webmanifest
│   └── service-worker.js
├── .env.example
├── .gitignore
└── README.md
```

## Security

No API keys or secrets are committed to the repository. The app needs no
external services to run.
