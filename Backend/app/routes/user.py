from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.databse import get_db
from app.models.db import User
from app.schemas.user import CreateUser, UpdateUser
from app.services.utils import hash_password
from typing import Optional

router = APIRouter(prefix="/user", tags=["user"])


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "marital_status": user.marital_status,
        "age": user.age,
        "current_income": user.current_income,
        "income_raise_pct": user.income_raise_pct,
        "current_monthly_expenses": user.current_monthly_expenses,
        "inflation_rate": user.inflation_rate,
        "spouse_age": user.spouse_age,
        "spouse_income": user.spouse_income,
        "spouse_income_raise_pct": user.spouse_income_raise_pct,
        "is_verified": user.is_verified,
        "is_active": user.is_active,
        "onboarding_complete": user.onboarding_complete,
        "onboarding_step": user.onboarding_step,
    }


@router.post("/", status_code=201)
def create_user(
    name: str = Form(..., description="Full name of the user"),
    email: str = Form(..., description="Email address of the user"),
    phone_number: str = Form(..., min_length=10, max_length=10, description="Phone number of the user without country code (10 digits)"),
    password: str = Form(..., min_length=6, description="Password for the user account (min 6 characters)"),
    current_monthly_expenses: float = Form(..., gt=0, description="Current Monthly Household Expenses"),
    inflation_rate: float = Form(6.0, gt=0, le=20, description="Expected Inflation Rate (%)"),
    marital_status: str = Form(..., description="'Single' or 'Married'"),
    age: int = Form(..., ge=18, le=80, description="Current Age"),
    current_income: float = Form(..., gt=0, description="Current Annual Income"),
    income_raise_pct: float = Form(..., ge=0, le=50, description="Expected Annual Income Raise (%)"),
    spouse_age: Optional[int] = Form(None, ge=18, le=80),
    spouse_income: Optional[float] = Form(None, ge=0),
    spouse_income_raise_pct: Optional[float] = Form(None, ge=0, le=50),
    db: Session = Depends(get_db),
):
    data = CreateUser(
        name=name,
        email=email,
        phone_number=phone_number,
        password=password,
        current_monthly_expenses=current_monthly_expenses,
        inflation_rate=inflation_rate,
        marital_status=marital_status,
        age=age,
        current_income=current_income,
        income_raise_pct=income_raise_pct,
        spouse_age=spouse_age,
        spouse_income=spouse_income,
        spouse_income_raise_pct=spouse_income_raise_pct,
    )
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User with this email already exists")

    user = User(
        full_name=data.name,
        email=data.email,
        phone_number=data.phone_number,
        hashed_password=hash_password(data.password),
        marital_status=data.marital_status,
        age=data.age,
        current_income=data.current_income,
        income_raise_pct=data.income_raise_pct,
        current_monthly_expenses=data.current_monthly_expenses,
        inflation_rate=data.inflation_rate,
        spouse_age=data.spouse_age,
        spouse_income=data.spouse_income,
        spouse_income_raise_pct=data.spouse_income_raise_pct,
        onboarding_complete=True,
        onboarding_step=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user_id": user.id, "message": "User created successfully", "user": _serialize_user(user)}


@router.get("/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db)):
    """Fetch a user profile by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "user": _serialize_user(user)}


@router.put("/{user_id}")
def update_user(
    user_id: str,
    marital_status: Optional[str] = Form(None, description="'Single' or 'Married'"),
    age: Optional[int] = Form(None, ge=18, le=80),
    current_income: Optional[float] = Form(None, gt=0),
    income_raise_pct: Optional[float] = Form(None, ge=0, le=50),
    current_monthly_expenses: Optional[float] = Form(None, gt=0),
    inflation_rate: Optional[float] = Form(None, gt=0, le=20),
    spouse_age: Optional[int] = Form(None, ge=18, le=80),
    spouse_income: Optional[float] = Form(None, ge=0),
    spouse_income_raise_pct: Optional[float] = Form(None, ge=0, le=50),
    db: Session = Depends(get_db),
):
    """Update an existing user profile (partial update — only fill fields you want to change)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = UpdateUser(
        marital_status=marital_status,
        age=age,
        current_income=current_income,
        income_raise_pct=income_raise_pct,
        current_monthly_expenses=current_monthly_expenses,
        inflation_rate=inflation_rate,
        spouse_age=spouse_age,
        spouse_income=spouse_income,
        spouse_income_raise_pct=spouse_income_raise_pct,
    )
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    if "marital_status" in update_data:
        user.marital_status = update_data["marital_status"]
    if "age" in update_data:
        user.age = update_data["age"]
    if "current_income" in update_data:
        user.current_income = update_data["current_income"]
    if "income_raise_pct" in update_data:
        user.income_raise_pct = update_data["income_raise_pct"]
    if "current_monthly_expenses" in update_data:
        user.current_monthly_expenses = update_data["current_monthly_expenses"]
    if "inflation_rate" in update_data:
        user.inflation_rate = update_data["inflation_rate"]
    if "spouse_age" in update_data:
        user.spouse_age = update_data["spouse_age"]
    if "spouse_income" in update_data:
        user.spouse_income = update_data["spouse_income"]
    if "spouse_income_raise_pct" in update_data:
        user.spouse_income_raise_pct = update_data["spouse_income_raise_pct"]

    db.commit()
    db.refresh(user)
    return {"user_id": user_id, "message": "User updated successfully", "user": _serialize_user(user)}


@router.delete("/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db)):
    """Delete a user profile by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"user_id": user_id, "message": "User deleted successfully"}


@router.get("/")
def list_users(db: Session = Depends(get_db)):
    """List all users."""
    users = db.query(User).all()
    return {"users": [_serialize_user(user) for user in users]}
