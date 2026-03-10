from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.databse import Base, engine
from app.models import db as db_models
from app.routes.auth import router as auth_router
from app.routes.calaculation import router as calculation_router
from app.routes.user import router as user_router
from app.routes.goals import router as goals_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calculation_router)
app.include_router(user_router)
app.include_router(goals_router)
app.include_router(auth_router)


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)

@app.get("/")
def read_root():
    return {"Message": "Welcome to Financial Planning API"}
