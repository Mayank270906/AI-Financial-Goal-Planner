from fastapi import FastAPI
from app.routes.calaculation import router as calculation_router
from app.routes.user import router as user_router
from app.routes.goals import router as goals_router

app = FastAPI()

app.include_router(calculation_router)
app.include_router(user_router)
app.include_router(goals_router)

@app.get("/")
def read_root():
    return {"Message": "Welcome to Financial Planning API"}
