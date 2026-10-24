from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    currency = Column(String, nullable=False, default="₹")

    # Deleting a group removes everything that belongs to it.
    members = relationship(
        "Member", back_populates="group", cascade="all, delete-orphan", order_by="Member.id"
    )
    expenses = relationship("Expense", back_populates="group", cascade="all, delete-orphan")
    settlements = relationship("Settlement", back_populates="group", cascade="all, delete-orphan")


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        # Names identify people in the UI, so they must be unique inside a group.
        UniqueConstraint("group_id", "name", name="uq_member_name_per_group"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)

    group = relationship("Group", back_populates="members")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_expense_amount_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, nullable=False)
    # Money is stored as integer cents (paise) so splits never suffer float rounding.
    amount_cents = Column(Integer, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    paid_by_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    group = relationship("Group", back_populates="expenses")
    paid_by = relationship("Member")
    shares = relationship(
        "ExpenseShare", back_populates="expense", cascade="all, delete-orphan", order_by="ExpenseShare.id"
    )


class ExpenseShare(Base):
    __tablename__ = "expense_shares"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    share_cents = Column(Integer, nullable=False)

    expense = relationship("Expense", back_populates="shares")


class Settlement(Base):
    """A repayment: one member paid another back outside the app."""

    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_settlement_amount_positive"),
        CheckConstraint("from_member_id != to_member_id", name="ck_settlement_distinct_members"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    from_member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    to_member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    group = relationship("Group", back_populates="settlements")
