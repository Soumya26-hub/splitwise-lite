import logging

from sqlalchemy import event

from backend.database import engine


def count_queries(action):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return len(statements)


def test_expense_list_query_count_does_not_grow_with_expenses(client):
    group = client.post("/groups/", json={"name": "Trip", "members": ["Asha", "Ben"]}).json()
    url = f"/groups/{group['id']}/expenses"
    payer = group["members"][0]["id"]

    client.post(url, json={"description": "Taxi", "amount": 50, "paid_by_id": payer})
    with_one = count_queries(lambda: client.get(url))
    for number in range(5):
        client.post(url, json={"description": f"Meal {number}", "amount": 20, "paid_by_id": payer})
    with_six = count_queries(lambda: client.get(url))

    assert len(client.get(url).json()) == 6
    assert with_six == with_one


def test_requests_and_rule_errors_are_logged(client, caplog):
    caplog.set_level(logging.INFO, logger="splitwise")
    client.get("/groups/")
    client.post("/groups/join/not-a-code")

    messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("GET /groups/ 200") for message in messages)
    assert any("rejected: This invite link is not valid." in message for message in messages)
