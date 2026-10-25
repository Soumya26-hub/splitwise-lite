"""
Business rules for members, expenses and settlements.

Routes in main.py stay thin: they check who is signed in, call one function here
and return the result. A broken rule raises a ServiceError subclass, which main.py
turns into an HTTP response, so these rules can be tested without HTTP.
"""

from sqlalchemy.orm import Session

from . import crud
from .schemas import ExpenseCreate, MemberCreate, SettlementCreate


class ServiceError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(ServiceError):
    status_code = 404


class Forbidden(ServiceError):
    status_code = 403


class Conflict(ServiceError):
    status_code = 409


class InvalidRequest(ServiceError):
    status_code = 422


def ensure_members_in_group(group, member_ids):
    group_member_ids = {member.id for member in group.members}
    if not set(member_ids) <= group_member_ids:
        raise InvalidRequest("Every member must belong to this group.")


# Groups and members

def join_group(db: Session, invite_code: str, user):
    group = crud.get_group_by_invite(db, invite_code)
    if group is None:
        raise NotFound("This invite link is not valid.")
    if crud.link_user_to_group(db, group, user) is None:
        raise Conflict(f"Someone else already joined as {user.name}. Sign in with a different name.")
    return group


def add_member(db: Session, group, member_data: MemberCreate):
    new_user = crud.get_user(db, member_data.user_id)
    if new_user is None:
        raise NotFound("User not found")
    if crud.my_member(group, new_user) is not None:
        raise Conflict(f"{new_user.name} is already in the group.")
    member = crud.link_user_to_group(db, group, new_user)
    if member is None:
        raise Conflict(f"Someone else named {new_user.name} is already in the group.")
    return {"id": member.id, "name": member.name, "joined": True, "phone": new_user.phone}


def remove_member(db: Session, group, member_id: int):
    member = crud.get_member(db, group.id, member_id)
    if member is None:
        raise NotFound("Member not found")
    # Removing someone with history would silently change everyone else's balance.
    if crud.member_has_activity(db, member.id):
        raise Conflict("This member has expenses or payments and cannot be removed.")
    crud.delete_member(db, member)


# Expenses

def create_expense(db: Session, group, expense_data: ExpenseCreate):
    if not group.members:
        raise InvalidRequest("Add members to the group before adding expenses.")
    ensure_members_in_group(group, [expense_data.paid_by_id, *(expense_data.split_between or [])])
    return crud.create_expense(db, group, expense_data)


def delete_expense(db: Session, group, expense_id: int):
    expense = crud.get_expense(db, group.id, expense_id)
    if expense is None:
        raise NotFound("Expense not found")
    crud.delete_expense(db, expense)


def respond_to_expense(db: Session, group, user, expense_id: int, decision: str):
    expense = crud.get_expense(db, group.id, expense_id)
    if expense is None:
        raise NotFound("Expense not found")
    # You can only answer for your own share.
    my_member_id = crud.my_member(group, user).id
    share = next((share for share in expense.shares if share.member_id == my_member_id), None)
    if share is None:
        raise NotFound("You are not in this split")
    if share.status != "pending":
        raise Conflict(f"This share was already {share.status}.")
    if decision == "reject" and sum(s.status != "rejected" for s in expense.shares) == 1:
        raise Conflict("The last person in a split cannot reject it. Delete the expense instead.")
    return crud.respond_to_share(db, expense, share, decision)


# Settlements (recorded repayments)

def create_settlement(db: Session, group, user, settlement_data: SettlementCreate):
    if settlement_data.from_member_id == settlement_data.to_member_id:
        raise InvalidRequest("A member cannot pay themselves.")
    ensure_members_in_group(group, [settlement_data.from_member_id, settlement_data.to_member_id])
    my_member_id = crud.my_member(group, user).id
    return crud.create_settlement(db, group.id, settlement_data, my_member_id)


def confirm_settlement(db: Session, group, user, settlement_id: int):
    settlement = crud.get_settlement(db, group.id, settlement_id)
    if settlement is None:
        raise NotFound("Settlement not found")
    # Only the person who received the money can say it arrived.
    if settlement.to_member_id != crud.my_member(group, user).id:
        raise Forbidden("Only the person who was paid can confirm this payment.")
    return crud.confirm_settlement(db, settlement)


def delete_settlement(db: Session, group, settlement_id: int):
    settlement = crud.get_settlement(db, group.id, settlement_id)
    if settlement is None:
        raise NotFound("Settlement not found")
    crud.delete_settlement(db, settlement)
