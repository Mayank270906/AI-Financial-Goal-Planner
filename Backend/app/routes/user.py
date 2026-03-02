from fastapi import HTTPException, APIRouter, Form
from app.models.user import CreateUser, UpdateUser
from typing import Optional
from uuid import uuid4

router = APIRouter(prefix="/user", tags=["user"])

# In-memory store (no database for now)
users_db: dict = {}


@router.post("/", status_code=201)
def create_user(
    marital_status: str = Form(..., description="'Single' or 'Married'"),
    age: int = Form(..., ge=18, le=80, description="Current Age"),
    current_income: float = Form(..., gt=0, description="Current Annual Income"),
    income_raise_pct: float = Form(..., ge=0, le=50, description="Expected Annual Income Raise (%)"),
    spouse_age: Optional[int] = Form(None, ge=18, le=80),
    spouse_income: Optional[float] = Form(None, ge=0),
    spouse_income_raise_pct: Optional[float] = Form(None, ge=0, le=50),
):
    data = CreateUser(
        marital_status=marital_status,
        age=age,
        current_income=current_income,
        income_raise_pct=income_raise_pct,
        spouse_age=spouse_age,
        spouse_income=spouse_income,
        spouse_income_raise_pct=spouse_income_raise_pct,
    )
    user_id = str(uuid4())
    users_db[user_id] = data.model_dump()
    return {"user_id": user_id, "message": "User created successfully", "user": users_db[user_id]}


@router.get("/{user_id}")
def get_user(user_id: str):
    """Fetch a user profile by ID."""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "user": users_db[user_id]}


@router.put("/{user_id}")
def update_user(
    user_id: str,
    marital_status: Optional[str] = Form(None, description="'Single' or 'Married'"),
    age: Optional[int] = Form(None, ge=18, le=80),
    current_income: Optional[float] = Form(None, gt=0),
    income_raise_pct: Optional[float] = Form(None, ge=0, le=50),
    spouse_age: Optional[int] = Form(None, ge=18, le=80),
    spouse_income: Optional[float] = Form(None, ge=0),
    spouse_income_raise_pct: Optional[float] = Form(None, ge=0, le=50),
):
    """Update an existing user profile (partial update — only fill fields you want to change)."""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    data = UpdateUser(
        marital_status=marital_status,
        age=age,
        current_income=current_income,
        income_raise_pct=income_raise_pct,
        spouse_age=spouse_age,
        spouse_income=spouse_income,
        spouse_income_raise_pct=spouse_income_raise_pct,
    )
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    users_db[user_id].update(update_data)
    return {"user_id": user_id, "message": "User updated successfully", "user": users_db[user_id]}


@router.delete("/{user_id}")
def delete_user(user_id: str):
    """Delete a user profile by ID."""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    del users_db[user_id]
    return {"user_id": user_id, "message": "User deleted successfully"}


@router.get("/")
def list_users():
    """List all users."""
    return {"users": users_db}
