from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("name must not be empty")
    return value


def cents_to_amount(cents: int) -> float:
    return round(cents / 100, 2)


def amount_to_cents(amount: Decimal) -> int:
    return int(amount * 100)


# Positive, at most 2 decimal places, below one crore: enough for any shared bill.
Amount = Field(gt=0, lt=10_000_000, max_digits=10, decimal_places=2)


class MemberCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_name(value)


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class GroupCreate(BaseModel):
    name: str
    currency: str = Field(default="₹", min_length=1, max_length=3)
    members: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_name(value)

    @field_validator("members")
    @classmethod
    def validate_members(cls, value: list[str]) -> list[str]:
        names = [normalize_name(name) for name in value]
        if len({name.lower() for name in names}) != len(names):
            raise ValueError("member names must be unique")
        return names


class GroupSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    currency: str


class GroupRead(GroupSummary):
    members: list[MemberRead]


class ExpenseCreate(BaseModel):
    description: str
    amount: Decimal = Amount
    paid_by_id: int
    # Members sharing the cost; omit to split between everyone in the group.
    split_between: list[int] | None = None

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("description must not be empty")
        return value

    @field_validator("split_between")
    @classmethod
    def validate_split_between(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("split_between must name at least one member")
        if len(set(value)) != len(value):
            raise ValueError("split_between must not repeat a member")
        return value


class ExpenseShareRead(BaseModel):
    member_id: int
    amount: float


class ExpenseRead(BaseModel):
    id: int
    description: str
    amount: float
    paid_by_id: int
    created_at: datetime
    shares: list[ExpenseShareRead]


class SettlementCreate(BaseModel):
    from_member_id: int
    to_member_id: int
    amount: Decimal = Amount


class SettlementRead(BaseModel):
    id: int
    from_member_id: int
    to_member_id: int
    amount: float
    created_at: datetime


class MemberBalance(BaseModel):
    member_id: int
    name: str
    # Positive: the group owes this member. Negative: this member owes the group.
    balance: float


class SuggestedPayment(BaseModel):
    from_member_id: int
    to_member_id: int
    amount: float


class GroupBalances(BaseModel):
    group_id: int
    total_spent: float
    balances: list[MemberBalance]
    settle_up: list[SuggestedPayment]
