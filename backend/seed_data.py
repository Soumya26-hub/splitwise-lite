from decimal import Decimal

from . import crud
from .models import Group
from .schemas import ExpenseCreate, GroupCreate


DEMO_GROUP = GroupCreate(name="Goa Trip", members=["Aditi", "Rohan", "Kavya", "Farhan"])

# (description, amount, payer name, names sharing it or None for everyone)
DEMO_EXPENSES = [
    ("Beach shack dinner", "2400.00", "Aditi", None),
    ("Scooter rental", "1500.00", "Rohan", ["Rohan", "Kavya", "Farhan"]),
    ("Groceries", "860.50", "Kavya", None),
]


def seed_if_empty(db):
    """Add a demo group with a few expenses only when no groups exist."""
    if db.query(Group).first() is not None:
        return

    group = crud.create_group(db, DEMO_GROUP)
    ids_by_name = {member.name: member.id for member in group.members}
    for description, amount, payer, shared_by in DEMO_EXPENSES:
        crud.create_expense(
            db,
            group,
            ExpenseCreate(
                description=description,
                amount=Decimal(amount),
                paid_by_id=ids_by_name[payer],
                split_between=[ids_by_name[name] for name in shared_by] if shared_by else None,
            ),
        )
