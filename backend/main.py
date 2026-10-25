import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import crud
from .database import Base, SessionLocal, add_missing_columns, engine
from .schemas import (
    ExpenseCreate,
    ExpenseRead,
    ShareResponse,
    GroupBalances,
    GroupCreate,
    GroupRead,
    GroupSummary,
    MemberCreate,
    MemberRead,
    SettlementCreate,
    SettlementRead,
    SignIn,
    SignInResult,
    UserRead,
)


# Run once when FastAPI starts: create tables and upgrade older databases.
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    add_missing_columns()
    yield


app = FastAPI(title="Splitwise Lite", lifespan=lifespan)
# The app is served from this server; CORS only matters when the frontend runs on Live Server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = crud.get_user_by_token(db, token) if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
    return user


def get_group_or_404(group_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    group = crud.get_group(db, group_id)
    # Groups you have not joined look the same as groups that do not exist.
    if group is None or crud.my_member(group, user) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


def ensure_members_in_group(group, member_ids):
    group_member_ids = {member.id for member in group.members}
    if not set(member_ids) <= group_member_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Every member must belong to this group.",
        )


# Sign in (name + phone, no password)

@app.post("/auth/signin", response_model=SignInResult)
def sign_in(sign_in_data: SignIn, db: Session = Depends(get_db)):
    user = crud.sign_in(db, sign_in_data)
    return {"token": user.token, "user": user}


@app.get("/auth/me", response_model=UserRead)
def read_me(user=Depends(get_current_user)):
    return user


# Groups

@app.post("/groups/", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(group_data: GroupCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return crud.group_to_dict(db, crud.create_group(db, group_data, user), user)


@app.get("/groups/", response_model=list[GroupSummary])
def read_groups(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return crud.get_groups_for_user(db, user)


@app.post("/groups/join/{invite_code}", response_model=GroupRead)
def join_group(invite_code: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    group = crud.get_group_by_invite(db, invite_code)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invite link is not valid.")
    if crud.link_user_to_group(db, group, user) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Someone else already joined as {user.name}. Sign in with a different name.",
        )
    return crud.group_to_dict(db, group, user)


@app.get("/groups/{group_id}", response_model=GroupRead)
def read_group(group=Depends(get_group_or_404), user=Depends(get_current_user), db: Session = Depends(get_db)):
    return crud.group_to_dict(db, group, user)


@app.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    crud.delete_group(db, group.id)


# Members

@app.post("/groups/{group_id}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def add_member(member_data: MemberCreate, group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    if crud.member_name_taken(db, group.id, member_data.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Someone with this name is already in the group.",
        )
    member = crud.add_member(db, group.id, member_data.name)
    return {"id": member.id, "name": member.name, "joined": False}


@app.delete("/groups/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: int, group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    member = crud.get_member(db, group.id, member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    # Removing someone with history would silently change everyone else's balance.
    if crud.member_has_activity(db, member.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This member has expenses or payments and cannot be removed.",
        )
    crud.delete_member(db, member)


# Expenses

@app.post("/groups/{group_id}/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(expense_data: ExpenseCreate, group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    if not group.members:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Add members to the group before adding expenses.",
        )
    ensure_members_in_group(group, [expense_data.paid_by_id, *(expense_data.split_between or [])])
    return crud.expense_to_dict(crud.create_expense(db, group, expense_data))


@app.get("/groups/{group_id}/expenses", response_model=list[ExpenseRead])
def read_expenses(group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    return [crud.expense_to_dict(expense) for expense in crud.get_expenses(db, group.id)]


@app.delete("/groups/{group_id}/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    expense = crud.get_expense(db, group.id, expense_id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    crud.delete_expense(db, expense)


@app.post("/groups/{group_id}/expenses/{expense_id}/respond", response_model=ExpenseRead)
def respond_to_expense(
    expense_id: int,
    response: ShareResponse,
    group=Depends(get_group_or_404),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expense = crud.get_expense(db, group.id, expense_id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    # You can only answer for your own share.
    my_member_id = crud.my_member(group, user).id
    share = next((share for share in expense.shares if share.member_id == my_member_id), None)
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You are not in this split")
    if share.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"This share was already {share.status}.")
    if response.decision == "reject" and sum(s.status != "rejected" for s in expense.shares) == 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last person in a split cannot reject it. Delete the expense instead.",
        )
    return crud.expense_to_dict(crud.respond_to_share(db, expense, share, response.decision))


# Settlements (recorded repayments)

@app.post(
    "/groups/{group_id}/settlements", response_model=SettlementRead, status_code=status.HTTP_201_CREATED
)
def create_settlement(
    settlement_data: SettlementCreate, group=Depends(get_group_or_404), db: Session = Depends(get_db)
):
    if settlement_data.from_member_id == settlement_data.to_member_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A member cannot pay themselves.",
        )
    ensure_members_in_group(group, [settlement_data.from_member_id, settlement_data.to_member_id])
    return crud.settlement_to_dict(crud.create_settlement(db, group.id, settlement_data))


@app.get("/groups/{group_id}/settlements", response_model=list[SettlementRead])
def read_settlements(group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    return [crud.settlement_to_dict(settlement) for settlement in crud.get_settlements(db, group.id)]


@app.delete("/groups/{group_id}/settlements/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_settlement(settlement_id: int, group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    settlement = crud.get_settlement(db, group.id, settlement_id)
    if settlement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement not found")
    crud.delete_settlement(db, settlement)


# Balances

@app.get("/groups/{group_id}/balances", response_model=GroupBalances)
def read_balances(group=Depends(get_group_or_404), db: Session = Depends(get_db)):
    return crud.get_group_balances(db, group)


# Windows can map .js to text/plain in its registry, which stops browsers running app.js.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")
frontend_directory = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")
