def create_group(client, **overrides):
    payload = {"name": "Flatmates", "members": ["Asha", "Ben", "Chen"]}
    payload.update(overrides)
    return client.post("/groups/", json=payload)


def test_demo_group_is_seeded(client):
    groups = client.get("/groups/").json()
    assert [group["name"] for group in groups] == ["Goa Trip"]


def test_create_and_read_group(client):
    response = create_group(client)
    assert response.status_code == 201
    group = response.json()
    assert group["currency"] == "₹"
    assert [member["name"] for member in group["members"]] == ["Asha", "Ben", "Chen"]
    assert client.get(f"/groups/{group['id']}").json() == group


def test_group_rejects_blank_name_and_duplicate_members(client):
    assert create_group(client, name="  ").status_code == 422
    assert create_group(client, members=["Asha", "asha"]).status_code == 422


def test_missing_group_returns_404(client):
    assert client.get("/groups/9999").status_code == 404
    assert client.get("/groups/9999/balances").status_code == 404
    assert client.delete("/groups/9999").status_code == 404


def test_add_member_rejects_duplicate_name(client):
    group = create_group(client).json()
    assert client.post(f"/groups/{group['id']}/members", json={"name": "Dev"}).status_code == 201
    assert client.post(f"/groups/{group['id']}/members", json={"name": " ben "}).status_code == 409


def test_member_with_activity_cannot_be_removed(client):
    group = create_group(client).json()
    asha, ben, chen = (member["id"] for member in group["members"])
    client.post(
        f"/groups/{group['id']}/expenses",
        json={"description": "Milk", "amount": 60, "paid_by_id": asha, "split_between": [asha, ben]},
    )
    assert client.delete(f"/groups/{group['id']}/members/{ben}").status_code == 409
    assert client.delete(f"/groups/{group['id']}/members/{chen}").status_code == 204
    assert client.delete(f"/groups/{group['id']}/members/{chen}").status_code == 404


def test_delete_group_with_history(client):
    group = client.get("/groups/").json()[0]
    members = client.get(f"/groups/{group['id']}").json()["members"]
    client.post(
        f"/groups/{group['id']}/settlements",
        json={"from_member_id": members[1]["id"], "to_member_id": members[0]["id"], "amount": 100},
    )
    assert client.delete(f"/groups/{group['id']}").status_code == 204
    assert client.get("/groups/").json() == []
