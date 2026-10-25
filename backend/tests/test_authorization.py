import pytest

from backend.tests.conftest import sign_in


@pytest.fixture
def group(client):
    return client.post("/groups/", json={"name": "Flatmates", "members": ["Asha", "Ben"]}).json()


def test_non_member_cannot_read_or_change_a_group(client, group):
    # Dev is signed in but has not joined the group, so it must look like it does not exist.
    dev = sign_in(client, "Dev", "9000000003")
    base = f"/groups/{group['id']}"
    asha = group["members"][0]["id"]
    ben = group["members"][1]["id"]

    assert client.get(base, headers=dev).status_code == 404
    assert client.get(f"{base}/balances", headers=dev).status_code == 404
    assert client.get(f"{base}/expenses", headers=dev).status_code == 404
    assert client.get(f"{base}/settlements", headers=dev).status_code == 404
    expense = {"description": "Taxi", "amount": 50, "paid_by_id": asha}
    assert client.post(f"{base}/expenses", json=expense, headers=dev).status_code == 404
    payment = {"from_member_id": ben, "to_member_id": asha, "amount": 10}
    assert client.post(f"{base}/settlements", json=payment, headers=dev).status_code == 404
    assert client.delete(base, headers=dev).status_code == 404

    # The group is untouched and still visible to its member.
    assert client.get(f"{base}/expenses").json() == []
    assert client.get(base).status_code == 200


def test_groups_list_shows_only_your_groups(client, group):
    dev = sign_in(client, "Dev", "9000000003")
    assert client.get("/groups/", headers=dev).json() == []
    assert [g["id"] for g in client.get("/groups/").json()] == [group["id"]]


def test_invalid_token_is_rejected(client):
    assert client.get("/groups/", headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401
