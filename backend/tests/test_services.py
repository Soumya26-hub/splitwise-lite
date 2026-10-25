from decimal import Decimal

import pytest

from backend import crud, services
from backend.database import SessionLocal
from backend.schemas import SettlementCreate
from backend.tests.conftest import sign_in


# These call the business rules directly, without going through HTTP.

@pytest.fixture
def db(client):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def group_and_users(client, db):
    group_id = client.post("/groups/", json={"name": "Trip", "members": ["Asha", "Ben"]}).json()["id"]
    ben_headers = sign_in(client, "Ben", "9000000002")
    invite_code = client.get(f"/groups/{group_id}").json()["invite_code"]
    client.post(f"/groups/join/{invite_code}", headers=ben_headers)
    group = crud.get_group(db, group_id)
    asha = crud.get_user_by_token(db, client.headers["Authorization"].removeprefix("Bearer "))
    ben = crud.get_user_by_token(db, ben_headers["Authorization"].removeprefix("Bearer "))
    return group, asha, ben


def test_member_cannot_pay_themselves(db, group_and_users):
    group, asha, _ = group_and_users
    me = crud.my_member(group, asha).id
    data = SettlementCreate(from_member_id=me, to_member_id=me, amount=Decimal("10"))
    with pytest.raises(services.InvalidRequest):
        services.create_settlement(db, group, asha, data)


def test_only_payee_can_confirm(db, group_and_users):
    group, asha, ben = group_and_users
    data = SettlementCreate(
        from_member_id=crud.my_member(group, ben).id,
        to_member_id=crud.my_member(group, asha).id,
        amount=Decimal("25"),
    )
    settlement = services.create_settlement(db, group, ben, data)
    assert settlement.status == "pending"
    with pytest.raises(services.Forbidden):
        services.confirm_settlement(db, group, ben, settlement.id)
    assert services.confirm_settlement(db, group, asha, settlement.id).status == "confirmed"


def test_missing_records_raise_not_found(db, group_and_users):
    group, asha, _ = group_and_users
    with pytest.raises(services.NotFound):
        services.delete_expense(db, group, 9999)
    with pytest.raises(services.NotFound):
        services.respond_to_expense(db, group, asha, 9999, "accept")
