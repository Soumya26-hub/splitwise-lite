import pytest

from backend.tests.conftest import sign_in


@pytest.fixture
def group(client):
    return client.post("/groups/", json={"name": "Flatmates", "members": ["Asha", "Ben", "Chen"]}).json()


def member_ids(group):
    return [member["id"] for member in group["members"]]


def add_expense(client, group, **overrides):
    payload = {"description": "Pizza", "amount": 100, "paid_by_id": member_ids(group)[0]}
    payload.update(overrides)
    return client.post(f"/groups/{group['id']}/expenses", json=payload)


def balances_by_name(client, group):
    data = client.get(f"/groups/{group['id']}/balances").json()
    return {item["name"]: item["balance"] for item in data["balances"]}, data


def test_expense_splits_between_everyone_by_default(client, group):
    response = add_expense(client, group)
    assert response.status_code == 201
    shares = [share["amount"] for share in response.json()["shares"]]
    assert shares == [33.34, 33.33, 33.33]

    balances, data = balances_by_name(client, group)
    assert balances == {"Asha": 66.66, "Ben": -33.33, "Chen": -33.33}
    assert data["total_spent"] == 100.0


def test_expense_split_between_some_members(client, group):
    asha, ben, chen = member_ids(group)
    add_expense(client, group, amount="45.50", paid_by_id=ben, split_between=[asha, ben])
    balances, _ = balances_by_name(client, group)
    assert balances == {"Asha": -22.75, "Ben": 22.75, "Chen": 0.0}


def test_settle_up_suggestions_and_recording_payment(client, group):
    asha, ben, chen = member_ids(group)
    add_expense(client, group, amount=300, paid_by_id=asha)
    _, data = balances_by_name(client, group)
    assert data["settle_up"] == [
        {"from_member_id": ben, "to_member_id": asha, "amount": 100.0},
        {"from_member_id": chen, "to_member_id": asha, "amount": 100.0},
    ]

    for payment in data["settle_up"]:
        assert client.post(f"/groups/{group['id']}/settlements", json=payment).status_code == 201
    balances, data = balances_by_name(client, group)
    assert set(balances.values()) == {0.0}
    assert data["settle_up"] == []


def test_invalid_expenses_rejected(client, group):
    asha = member_ids(group)[0]
    assert add_expense(client, group, amount=0).status_code == 422
    assert add_expense(client, group, amount="10.999").status_code == 422
    assert add_expense(client, group, description=" ").status_code == 422
    assert add_expense(client, group, split_between=[]).status_code == 422
    assert add_expense(client, group, split_between=[asha, asha]).status_code == 422
    # Members from another group are not allowed.
    outsider = client.post("/groups/", json={"name": "Other", "members": ["Zed"]}).json()["members"][0]["id"]
    assert add_expense(client, group, paid_by_id=outsider).status_code == 422
    assert add_expense(client, group, split_between=[asha, outsider]).status_code == 422


def test_settlement_validation(client, group):
    asha, ben, _ = member_ids(group)
    url = f"/groups/{group['id']}/settlements"
    assert client.post(url, json={"from_member_id": asha, "to_member_id": asha, "amount": 5}).status_code == 422
    assert client.post(url, json={"from_member_id": asha, "to_member_id": 9999, "amount": 5}).status_code == 422
    assert client.post(url, json={"from_member_id": asha, "to_member_id": ben, "amount": -5}).status_code == 422


def test_list_and_delete_expense_and_settlement(client, group):
    asha, ben, _ = member_ids(group)
    first = add_expense(client, group, description="First").json()
    add_expense(client, group, description="Second")
    expenses = client.get(f"/groups/{group['id']}/expenses").json()
    assert [expense["description"] for expense in expenses] == ["Second", "First"]

    assert client.delete(f"/groups/{group['id']}/expenses/{first['id']}").status_code == 204
    assert client.delete(f"/groups/{group['id']}/expenses/{first['id']}").status_code == 404

    settlement = client.post(
        f"/groups/{group['id']}/settlements",
        json={"from_member_id": ben, "to_member_id": asha, "amount": 10},
    ).json()
    assert len(client.get(f"/groups/{group['id']}/settlements").json()) == 1
    assert client.delete(f"/groups/{group['id']}/settlements/{settlement['id']}").status_code == 204
    assert client.get(f"/groups/{group['id']}/settlements").json() == []



def join_as(client, group, name, phone):
    headers = sign_in(client, name, phone)
    client.post(f"/groups/join/{group['invite_code']}", headers=headers)
    return headers


def respond(client, group, expense, headers, decision):
    return client.post(
        f"/groups/{group['id']}/expenses/{expense['id']}/respond",
        json={"decision": decision},
        headers=headers,
    )


def test_new_expense_shares_are_pending_except_payer(client, group):
    expense = add_expense(client, group).json()
    assert [share["status"] for share in expense["shares"]] == ["accepted", "pending", "pending"]


def test_accept_share(client, group):
    ben = join_as(client, group, "Ben", "9000000002")
    expense = add_expense(client, group).json()
    response = respond(client, group, expense, ben, "accept")
    assert response.status_code == 200
    assert response.json()["shares"][1]["status"] == "accepted"
    assert respond(client, group, expense, ben, "reject").status_code == 409


def test_reject_resplits_between_the_rest(client, group):
    chen = join_as(client, group, "Chen", "9000000003")
    expense = add_expense(client, group, amount=90).json()
    shares = respond(client, group, expense, chen, "reject").json()["shares"]
    assert [(s["amount"], s["status"]) for s in shares] == [(45.0, "accepted"), (45.0, "pending"), (0.0, "rejected")]

    balances, _ = balances_by_name(client, group)
    assert balances == {"Asha": 45.0, "Ben": -45.0, "Chen": 0.0}


def test_only_your_own_share_can_be_answered(client, group):
    asha, ben, _ = member_ids(group)
    # Asha paid, so her share is already accepted and she cannot answer for Ben.
    expense = add_expense(client, group).json()
    assert respond(client, group, expense, {}, "reject").status_code == 409
    # Someone outside the split gets a 404.
    dev = join_as(client, group, "Dev", "9000000004")
    assert respond(client, group, expense, dev, "accept").status_code == 404


def test_last_person_cannot_reject(client, group):
    asha, ben, _ = member_ids(group)
    ben_headers = join_as(client, group, "Ben", "9000000002")
    expense = add_expense(client, group, paid_by_id=asha, split_between=[ben]).json()
    assert respond(client, group, expense, ben_headers, "reject").status_code == 409


def test_respond_validation(client, group):
    ben = join_as(client, group, "Ben", "9000000002")
    expense = add_expense(client, group).json()
    assert respond(client, group, expense, ben, "maybe").status_code == 422
    assert respond(client, group, {"id": 9999}, ben, "accept").status_code == 404


def test_payment_counts_only_after_recipient_confirms(client, group):
    asha, ben, chen = member_ids(group)
    ben_headers = join_as(client, group, "Ben", "9000000002")
    add_expense(client, group, amount=300, paid_by_id=asha)

    url = f"/groups/{group['id']}/settlements"
    payment = client.post(url, json={"from_member_id": ben, "to_member_id": asha, "amount": 100}, headers=ben_headers)
    assert payment.json()["status"] == "pending"
    balances, _ = balances_by_name(client, group)
    assert balances["Ben"] == -100.0

    # Ben cannot confirm his own payment; Asha, who was paid, can.
    assert client.post(f"{url}/{payment.json()['id']}/confirm", headers=ben_headers).status_code == 403
    confirmed = client.post(f"{url}/{payment.json()['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    balances, _ = balances_by_name(client, group)
    assert balances["Ben"] == 0.0


def test_payment_recorded_by_recipient_is_confirmed(client, group):
    asha, ben, _ = member_ids(group)
    payment = client.post(
        f"/groups/{group['id']}/settlements", json={"from_member_id": ben, "to_member_id": asha, "amount": 10}
    )
    assert payment.json()["status"] == "confirmed"
