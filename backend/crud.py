from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .algorithms import compute_balances, simplify_debts, split_equally
from .models import Expense, ExpenseShare, Group, Member, Settlement, User, new_secret
from .schemas import (
    ExpenseCreate,
    GroupCreate,
    SettlementCreate,
    SignIn,
    amount_to_cents,
    cents_to_amount,
)


def sign_in(db: Session, sign_in_data: SignIn):
    """Find the user by phone, or create them. The phone number is the identity."""
    user = db.query(User).filter(User.phone == sign_in_data.phone).first()
    if user is None:
        user = User(name=sign_in_data.name, phone=sign_in_data.phone)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def search_users(db: Session, query: str, limit: int = 10):
    return (
        db.query(User)
        .filter(User.name.ilike(f"%{query.strip()}%"))
        .order_by(User.name, User.id)
        .limit(limit)
        .all()
    )


def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_token(db: Session, token: str):
    return db.query(User).filter(User.token == token).first()


def find_member_by_name(group: Group, name: str):
    return next((member for member in group.members if member.name.lower() == name.lower()), None)


def link_user_to_group(db: Session, group: Group, user: User):
    """Make the user a member: claim the unclaimed member with their name, or add them."""
    member = next((member for member in group.members if member.user_id == user.id), None)
    if member is not None:
        return member
    member = find_member_by_name(group, user.name)
    if member is None:
        member = Member(name=user.name, group_id=group.id)
        group.members.append(member)
    elif member.user_id is not None:
        return None
    member.user_id = user.id
    db.commit()
    db.refresh(group)
    return member


def create_group(db: Session, group_data: GroupCreate, user: User):
    group = Group(name=group_data.name, currency=group_data.currency)
    group.members = [Member(name=name) for name in group_data.members]
    db.add(group)
    db.commit()
    db.refresh(group)
    link_user_to_group(db, group, user)
    return group


def get_groups_for_user(db: Session, user: User):
    return (
        db.query(Group)
        .join(Member, Member.group_id == Group.id)
        .filter(Member.user_id == user.id)
        .order_by(Group.id)
        .all()
    )


def get_group_by_invite(db: Session, invite_code: str):
    return db.query(Group).filter(Group.invite_code == invite_code).first()


def my_member(group: Group, user: User):
    return next((member for member in group.members if member.user_id == user.id), None)


def group_to_dict(db: Session, group: Group, user: User):
    if group.invite_code is None:
        # Groups created before invite links existed get one on first read.
        group.invite_code = new_secret()
        db.commit()
    return {
        "id": group.id,
        "name": group.name,
        "currency": group.currency,
        "invite_code": group.invite_code,
        "my_member_id": my_member(group, user).id,
        "members": [
            {
                "id": member.id,
                "name": member.name,
                "joined": member.user_id is not None,
                "phone": member.user.phone if member.user else None,
            }
            for member in group.members
        ],
    }


def get_group(db: Session, group_id: int):
    return db.query(Group).filter(Group.id == group_id).first()


def delete_group(db: Session, group_id: int):
    group = get_group(db, group_id)
    if group is None:
        return None

    # Expenses and settlements point at members, so remove them before the members go.
    group.settlements.clear()
    group.expenses.clear()
    db.flush()
    db.delete(group)
    db.commit()
    return group


def get_member(db: Session, group_id: int, member_id: int):
    return db.query(Member).filter(Member.group_id == group_id, Member.id == member_id).first()


def member_has_activity(db: Session, member_id: int):
    paid = db.query(Expense.id).filter(Expense.paid_by_id == member_id).first()
    shared = db.query(ExpenseShare.id).filter(ExpenseShare.member_id == member_id).first()
    settled = (
        db.query(Settlement.id)
        .filter(or_(Settlement.from_member_id == member_id, Settlement.to_member_id == member_id))
        .first()
    )
    return any(row is not None for row in (paid, shared, settled))


def delete_member(db: Session, member: Member):
    db.delete(member)
    db.commit()


def create_expense(db: Session, group: Group, expense_data: ExpenseCreate):
    split_between = expense_data.split_between or [member.id for member in group.members]
    amount_cents = amount_to_cents(expense_data.amount)
    shares = split_equally(amount_cents, split_between)

    expense = Expense(
        description=expense_data.description,
        amount_cents=amount_cents,
        group_id=group.id,
        paid_by_id=expense_data.paid_by_id,
    )
    # The payer obviously agrees with their own expense; everyone else confirms it.
    expense.shares = [
        ExpenseShare(
            member_id=member_id,
            share_cents=share_cents,
            status="accepted" if member_id == expense.paid_by_id else "pending",
        )
        for member_id, share_cents in shares.items()
    ]
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def get_expenses(db: Session, group_id: int):
    # Newest first, which is how the app's activity list shows them.
    return (
        db.query(Expense)
        .filter(Expense.group_id == group_id)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .all()
    )


def get_expense(db: Session, group_id: int, expense_id: int):
    return db.query(Expense).filter(Expense.group_id == group_id, Expense.id == expense_id).first()


def respond_to_share(db: Session, expense: Expense, share: ExpenseShare, decision: str):
    if decision == "accept":
        share.status = "accepted"
    else:
        # Re-split the whole amount between everyone who has not rejected it.
        share.status = "rejected"
        share.share_cents = 0
        remaining = [s for s in expense.shares if s.status != "rejected"]
        new_shares = split_equally(expense.amount_cents, [s.member_id for s in remaining])
        for remaining_share in remaining:
            remaining_share.share_cents = new_shares[remaining_share.member_id]
    db.commit()
    db.refresh(expense)
    return expense


def delete_expense(db: Session, expense: Expense):
    db.delete(expense)
    db.commit()


def create_settlement(db: Session, group_id: int, settlement_data: SettlementCreate, recorded_by_id: int):
    settlement = Settlement(
        group_id=group_id,
        from_member_id=settlement_data.from_member_id,
        to_member_id=settlement_data.to_member_id,
        amount_cents=amount_to_cents(settlement_data.amount),
        # When the person who got the money records it, there is nothing left to confirm.
        status="confirmed" if recorded_by_id == settlement_data.to_member_id else "pending",
    )
    db.add(settlement)
    db.commit()
    db.refresh(settlement)
    return settlement


def get_settlements(db: Session, group_id: int):
    return (
        db.query(Settlement)
        .filter(Settlement.group_id == group_id)
        .order_by(Settlement.created_at.desc(), Settlement.id.desc())
        .all()
    )


def get_settlement(db: Session, group_id: int, settlement_id: int):
    return (
        db.query(Settlement)
        .filter(Settlement.group_id == group_id, Settlement.id == settlement_id)
        .first()
    )


def confirm_settlement(db: Session, settlement: Settlement):
    settlement.status = "confirmed"
    db.commit()
    db.refresh(settlement)
    return settlement


def delete_settlement(db: Session, settlement: Settlement):
    db.delete(settlement)
    db.commit()


def get_group_balances(db: Session, group: Group):
    expenses = get_expenses(db, group.id)
    settlements = get_settlements(db, group.id)
    balances = compute_balances(
        [member.id for member in group.members],
        (
            (expense.paid_by_id, expense.amount_cents, {s.member_id: s.share_cents for s in expense.shares})
            for expense in expenses
        ),
        # A payment only counts once the person paid has confirmed receiving it.
        ((s.from_member_id, s.to_member_id, s.amount_cents) for s in settlements if s.status == "confirmed"),
    )
    return {
        "group_id": group.id,
        "total_spent": cents_to_amount(sum(expense.amount_cents for expense in expenses)),
        "balances": [
            {"member_id": member.id, "name": member.name, "balance": cents_to_amount(balances[member.id])}
            for member in group.members
        ],
        "settle_up": [
            {"from_member_id": debtor, "to_member_id": creditor, "amount": cents_to_amount(amount)}
            for debtor, creditor, amount in simplify_debts(balances)
        ],
    }


def expense_to_dict(expense: Expense):
    return {
        "id": expense.id,
        "description": expense.description,
        "amount": cents_to_amount(expense.amount_cents),
        "paid_by_id": expense.paid_by_id,
        "created_at": expense.created_at,
        "shares": [
            {"member_id": share.member_id, "amount": cents_to_amount(share.share_cents), "status": share.status}
            for share in expense.shares
        ],
    }


def settlement_to_dict(settlement: Settlement):
    return {
        "id": settlement.id,
        "from_member_id": settlement.from_member_id,
        "to_member_id": settlement.to_member_id,
        "amount": cents_to_amount(settlement.amount_cents),
        "created_at": settlement.created_at,
        "status": settlement.status,
    }
