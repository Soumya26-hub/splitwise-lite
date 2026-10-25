from backend.tests.conftest import sign_in


def create_group(client, **overrides):
    payload = {"name": "Flatmates", "members": ["Asha", "Ben", "Chen"]}
    payload.update(overrides)
    return client.post("/groups/", json=payload)


def test_create_and_read_group(client):
    response = create_group(client)
    assert response.status_code == 201
    group = response.json()
    assert group["currency"] == "₹"
    assert [(m["name"], m["joined"]) for m in group["members"]] == [("Asha", True), ("Ben", False), ("Chen", False)]
    assert group["my_member_id"] == group["members"][0]["id"]
    assert client.get(f"/groups/{group['id']}").json() == group
    assert [g["name"] for g in client.get("/groups/").json()] == ["Flatmates"]


def test_creator_is_added_when_not_listed(client):
    group = create_group(client, members=["Ben"]).json()
    assert [member["name"] for member in group["members"]] == ["Ben", "Asha"]


def test_group_rejects_blank_name_and_duplicate_members(client):
    assert create_group(client, name="  ").status_code == 422
    assert create_group(client, members=["Asha", "asha"]).status_code == 422


def test_missing_group_returns_404(client):
    assert client.get("/groups/9999").status_code == 404
    assert client.get("/groups/9999/balances").status_code == 404
    assert client.delete("/groups/9999").status_code == 404


def test_requests_without_sign_in_are_rejected(client):
    assert client.get("/groups/", headers={"Authorization": ""}).status_code == 401
    assert client.get("/groups/", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_sign_in_validates_phone_and_reuses_account(client):
    assert client.post("/auth/signin", json={"name": "Ben", "phone": "123"}).status_code == 422
    first = client.post("/auth/signin", json={"name": "Ben", "phone": "+91 98765-43210"}).json()
    again = client.post("/auth/signin", json={"name": "Ben", "phone": "+919876543210"}).json()
    assert first == again
    assert first["user"]["phone"] == "+919876543210"
    assert client.get("/auth/me").json()["name"] == "Asha"


def test_invite_link_claims_member_with_same_name(client):
    group = create_group(client).json()
    ben = sign_in(client, "ben", "9000000002")
    assert client.get(f"/groups/{group['id']}", headers=ben).status_code == 404

    joined = client.post(f"/groups/join/{group['invite_code']}", headers=ben)
    assert joined.status_code == 200
    assert joined.json()["my_member_id"] == group["members"][1]["id"]
    assert len(joined.json()["members"]) == 3
    # Joining twice is harmless.
    assert client.post(f"/groups/join/{group['invite_code']}", headers=ben).status_code == 200


def test_invite_link_adds_new_member_and_rejects_name_clash(client):
    group = create_group(client).json()
    dev = sign_in(client, "Dev", "9000000003")
    assert len(client.post(f"/groups/join/{group['invite_code']}", headers=dev).json()["members"]) == 4

    other_asha = sign_in(client, "Asha", "9000000004")
    assert client.post(f"/groups/join/{group['invite_code']}", headers=other_asha).status_code == 409
    assert client.post("/groups/join/not-a-code", headers=dev).status_code == 404


def test_search_users_hides_phone_numbers(client):
    sign_in(client, "Ben Kumar", "9000000002")
    sign_in(client, "Bina", "9000000003")
    results = client.get("/users/search", params={"q": "bi"}).json()
    assert results == [{"id": 3, "name": "Bina"}]
    assert [user["name"] for user in client.get("/users/search", params={"q": "B"}).json()] == ["Ben Kumar", "Bina"]
    assert client.get("/users/search", params={"q": ""}).status_code == 422


def test_add_signed_in_user_as_member(client):
    group = create_group(client, members=[]).json()
    ben_id = client.post("/auth/signin", json={"name": "Ben", "phone": "9000000002"}).json()["user"]["id"]
    response = client.post(f"/groups/{group['id']}/members", json={"user_id": ben_id})
    assert response.status_code == 201
    assert response.json()["joined"] is True
    assert client.post(f"/groups/{group['id']}/members", json={"user_id": ben_id}).status_code == 409
    assert client.post(f"/groups/{group['id']}/members", json={"user_id": 9999}).status_code == 404
    # Made-up names can no longer be added.
    assert client.post(f"/groups/{group['id']}/members", json={"name": "Dummy"}).status_code == 422


def test_adding_user_claims_unjoined_member_with_same_name(client):
    group = create_group(client).json()
    ben_id = client.post("/auth/signin", json={"name": "ben", "phone": "9000000002"}).json()["user"]["id"]
    member = client.post(f"/groups/{group['id']}/members", json={"user_id": ben_id}).json()
    assert member["id"] == group["members"][1]["id"]


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
    group = create_group(client).json()
    asha, ben, _ = (member["id"] for member in group["members"])
    client.post(
        f"/groups/{group['id']}/expenses",
        json={"description": "Milk", "amount": 60, "paid_by_id": asha},
    )
    client.post(
        f"/groups/{group['id']}/settlements",
        json={"from_member_id": ben, "to_member_id": asha, "amount": 20},
    )
    assert client.delete(f"/groups/{group['id']}").status_code == 204
    assert client.get("/groups/").json() == []


def test_group_members_include_phone_once_joined(client):
    group = create_group(client).json()
    assert [member["phone"] for member in group["members"]] == ["9000000001", None, None]
    ben = sign_in(client, "Ben", "+919000000002")
    joined = client.post(f"/groups/join/{group['invite_code']}", headers=ben).json()
    assert joined["members"][1]["phone"] == "+919000000002"
