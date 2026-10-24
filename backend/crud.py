from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .algorithms import compute_balances, simplify_debts, split_equally
from .models import Expense, ExpenseShare, Group, Member, Settlement
from .schemas import (
    ExpenseCreate,
    GroupCreate,
    SettlementCreate,
    amount_to_cents,
    cents_to_amount,
)


def create_group(db: Session, group_data: GroupCreate):
    group = Group(name=group_data.name, currency=group_data.currency)
    group.members = [Member(name=name) for name in group_data.members]
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def get_groups(db: Session):
    return db.query(Group).order_by(Group.id).all()


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


def member_name_taken(db: Session, group_id: int, name: str):
    return (
        db.query(Member)
        .filter(Member.group_id == group_id, func.lower(Member.name) == name.lower())
        .first()
        is not None
    )


def add_member(db: Session, group_id: int, name: str):
    member = Member(group_id=group_id, name=name)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


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


def create_settlement(db: Session, group_id: int, settlement_data: SettlementCreate):
    settlement = Settlement(
        group_id=group_id,
        from_member_id=settlement_data.from_member_id,
        to_member_id=settlement_data.to_member_id,
        amount_cents=amount_to_cents(settlement_data.amount),
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
        ((s.from_member_id, s.to_member_id, s.amount_cents) for s in settlements),
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
    }
