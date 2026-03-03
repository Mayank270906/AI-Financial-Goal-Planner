from fastapi import APIRouter, Form, Body
from app.models.user import Retirement, ExplainRetirementRequest
from app.services.math.goals import get_retirement_plan, explain_retirement_plan_with_ai
from typing import Optional



router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("/retirement")
def endpoint_retirement(
    marital_status: str = Form(..., description="'Single' or 'Married'"),
    age: int = Form(..., ge=18, le=80, description="Current Age"),
    current_income: float = Form(..., gt=0, description="Current Annual Income"),
    income_raise_pct: float = Form(..., ge=0, le=50, description="Expected Annual Income Raise (%)"),
    spouse_age: Optional[int] = Form(None, ge=18, le=80),
    spouse_income: Optional[float] = Form(None, ge=0),
    spouse_income_raise_pct: Optional[float] = Form(None, ge=0, le=50),
    retirement_age: int = Form(..., ge=35, le=80, description="Target Retirement Age"),
    current_monthly_expenses: float = Form(..., gt=0, description="Current Monthly Household Expenses"),
    post_retirement_expense_pct: float = Form(..., gt=0, le=100, description="Post-retirement expenses as % of pre-retirement expenses"),
    inflation_rate: float = Form(6.0, gt=0, le=20, description="Expected Inflation Rate (%)"),
    post_retirement_return: float = Form(7.0, gt=0, le=20, description="Expected annual return on retirement corpus post-retirement (%)"),
    pre_retirement_return: float = Form(10.0, gt=0, le=20, description="Expected blended annual return on portfolio pre-retirement (%)"),
    life_expectancy: int = Form(..., ge=60, le=100, description="Life expectancy of the younger spouse (or self if single)"),
    annual_post_retirement_income: float = Form(0.0, ge=0, description="Annual post-retirement income (pension, rent, etc.) in today's value"),
    existing_corpus: float = Form(0.0, ge=0, description="Existing retirement corpus today"),
    existing_monthly_sip: float = Form(0.0, ge=0, description="Existing monthly SIP toward retirement"),
    sip_raise_pct: float = Form(0.0, ge=0, le=50, description="Annual step-up % on existing SIP (0 if no step-up)"),
):
    data = Retirement(
        marital_status=marital_status,
        age=age,
        current_income=current_income,
        income_raise_pct=income_raise_pct,
        spouse_age=spouse_age,
        spouse_income=spouse_income,
        spouse_income_raise_pct=spouse_income_raise_pct,
        retirement_age=retirement_age,
        current_monthly_expenses=current_monthly_expenses,
        post_retirement_expense_pct=post_retirement_expense_pct,
        inflation_rate=inflation_rate,
        post_retirement_return=post_retirement_return,
        pre_retirement_return=pre_retirement_return,
        life_expectancy=life_expectancy,
        annual_post_retirement_income=annual_post_retirement_income,
        existing_corpus=existing_corpus,
        existing_monthly_sip=existing_monthly_sip,
        sip_raise_pct=sip_raise_pct,
    )
    return get_retirement_plan(data)

@router.post("/explain_retirement_plan")
def endpoint_explain_retirement_plan(request: ExplainRetirementRequest):
    return {
        "explanation": explain_retirement_plan_with_ai(
            request.retirement_plan,
            request.user_question
        )
    }
