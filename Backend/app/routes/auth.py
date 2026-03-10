from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.databse import get_db
from app.models.db import User
from app.services.auth import create_access_token, verify_tokens
from app.services.utils import verify_password

from app.utils.log_format import JSONFormatter
import logging

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("auth_router")
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning({
            "event": "Failed login attempt",
            "username": form_data.username
        })
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.id})
    logger.info({
        "event": "Successful login",
        "username": form_data.username
    })
    return {"access_token": access_token, "token_type": "bearer"}

def decode_token(token: str = Depends(oauth2_scheme)):
    return verify_tokens(token)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    subject = verify_tokens(token)
    user = db.query(User).filter(User.id == subject).first()
    if not user:
        user = db.query(User).filter(User.email == subject).first()
    if not user:
        logger.warning({
            "event": "User not found for token",
            "token": token
        })
        raise HTTPException(status_code=401, detail="User not found for token")
    return user

@router.get('/profile')
def get_profile(user: User = Depends(get_current_user)):
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
        "onboarding_complete": user.onboarding_complete,
        "onboarding_step": user.onboarding_step,
    }