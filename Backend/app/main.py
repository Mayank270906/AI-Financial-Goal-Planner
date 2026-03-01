from fastapi import FastAPI
from routes.calaculation import router as calculation_router

app=FastAPI()

app.include_router(calculation_router)

@app.get("/")
def read_root():
    return {"Message":"Welcome to Financial Planning API"}

