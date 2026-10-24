import pytest


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
    assert add_expense(client, group, paid_by_id=1).status_code == 422
    assert add_expense(client, group, split_between=[asha, 1]).status_code == 422


def test_expense_needs_members(client):
    empty = client.post("/groups/", json={"name": "Empty"}).json()
    response = client.post(
        f"/groups/{empty['id']}/expenses", json={"description": "Tea", "amount": 10, "paid_by_id": 1}
    )
    assert response.status_code == 422


def test_settlement_validation(client, group):
    asha, ben, _ = member_ids(group)
    url = f"/groups/{group['id']}/settlements"
    assert client.post(url, json={"from_member_id": asha, "to_member_id": asha, "amount": 5}).status_code == 422
    assert client.post(url, json={"from_member_id": asha, "to_member_id": 1, "amount": 5}).status_code == 422
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
