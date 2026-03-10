from datetime import datetime, timedelta, timezone
import os

from fastapi import HTTPException, status
from authlib.jose import jwt
from authlib.jose.errors import JoseError
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")

JWT_SECRET_KEY = SECRET_KEY

def create_access_token(data:dict):
    header = {"alg": ALGORITHM}
    expire=datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)  
    payload=data.copy()
    payload.update({"exp": expire})
    token = jwt.encode(header, payload, JWT_SECRET_KEY)
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return token

def verify_tokens(token: str):
    try:
        claims = jwt.decode(token, JWT_SECRET_KEY)
        claims.validate()
        username = claims.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return username
    except JoseError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not verify credentials")


def verufy_tokens(token: str):
    return verify_tokens(token)