from fastapi import APIRouter, Form, Depends, HTTPException
from app.schemas.user import Retirement, ExplainRetirementRequest, ExplainOneTimeGoalRequest
from app.schemas.goals import OneTimeGoalRequest
from app.services.math.goals import get_retirement_plan, explain_retirement_plan_with_ai, save_retirement_plan, one_time_goal, explain_one_time_goal_with_ai, save_one_time_goal_plan
from app.databse import get_db
from app.models.db import User, GoalPlan
from typing import Optional
from app.routes.auth import get_current_user
from sqlalchemy.orm import Session
import json





router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("/retirement")
def endpoint_retirement(
    retirement_age: int = Form(..., ge=35, le=80, description="Target Retirement Age"),
    post_retirement_expense_pct: float = Form(..., gt=0, le=100, description="Post-retirement expenses as % of pre-retirement expenses"),
    post_retirement_return: float = Form(7.0, gt=0, le=20, description="Expected annual return on retirement corpus post-retirement (%)"),
    pre_retirement_return: float = Form(10.0, gt=0, le=20, description="Expected blended annual return on portfolio pre-retirement (%)"),
    life_expectancy: int = Form(..., ge=60, le=100, description="Life expectancy of the younger spouse (or self if single)"),
    annual_post_retirement_income: float = Form(0.0, ge=0, description="Annual post-retirement income (pension, rent, etc.) in today's value"),
    existing_corpus: float = Form(0.0, ge=0, description="Existing retirement corpus today"),
    existing_monthly_sip: float = Form(0.0, ge=0, description="Existing monthly SIP toward retirement"),
    sip_raise_pct: float = Form(0.0, ge=0, le=50, description="Annual step-up % on existing SIP (0 if no step-up)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    
    # User already fetched from DB by get_current_user dependency
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found. Please complete the onboarding first.")
    
    # Build Retirement object with user data from DB and endpoint parameters
    data = Retirement(
        name=current_user.full_name,
        email=current_user.email,
        phone_number=current_user.phone_number,
        password="placeholder",
        marital_status=current_user.marital_status,
        age=current_user.age,
        current_income=current_user.current_income,
        income_raise_pct=current_user.income_raise_pct,
        current_monthly_expenses=current_user.current_monthly_expenses,
        inflation_rate=current_user.inflation_rate,
        spouse_age=current_user.spouse_age,
        spouse_income=current_user.spouse_income,
        spouse_income_raise_pct=current_user.spouse_income_raise_pct,
        retirement_age=retirement_age,
        post_retirement_expense_pct=post_retirement_expense_pct,
        post_retirement_return=post_retirement_return,
        pre_retirement_return=pre_retirement_return,
        life_expectancy=life_expectancy,
        annual_post_retirement_income=annual_post_retirement_income,
        existing_corpus=existing_corpus,
        existing_monthly_sip=existing_monthly_sip,
        sip_raise_pct=sip_raise_pct,
    )
    
    # Calculate retirement plan
    plan = get_retirement_plan(data)
    
    # Save plan to database as JSON
    try:
        # Convert plan to JSON string for storage
        if isinstance(plan, str):
            plan_json = plan
        else:
            plan_json = json.dumps(plan, default=str)  # Use default=str for non-serializable objects
        
        save_retirement_plan(
            db=db,
            user_id=current_user.id,
            plan=plan_json,
            retirement_age=retirement_age,
        )
        print(f"✓ Retirement plan saved for user {current_user.id}")
    except Exception as e:
        # Log error but don't fail the response - plan calculation is more important
        print(f"Warning: Failed to save retirement plan to database: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return plan

@router.post("/explain_retirement_plan")
def endpoint_explain_retirement_plan(request: ExplainRetirementRequest):
    return {
        "explanation": explain_retirement_plan_with_ai(
            request.retirement_plan,
            request.user_question
        )
    }

@router.post("/one_time_goal")
def endpoint_one_time_goal(
    goal_name: str = Form(..., description="Name of the goal (e.g., 'Buy a Car', 'House Down Payment')"),
    goal_amount: float = Form(..., gt=0, description="Goal amount in today's value"),
    years_to_goal: float = Form(..., gt=0, le=50, description="Years until goal is needed"),
    pre_ret_return: float = Form(10.0, gt=0, le=20, description="Expected annual return on investments (%)"),
    existing_corpus: float = Form(0.0, ge=0, description="Existing savings toward this goal"),
    existing_monthly_sip: float = Form(0.0, ge=0, description="Existing monthly SIP for this goal"),
    risk_tolerance: str = Form("moderate", description="Risk tolerance: low, moderate, high"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    # User already fetched from DB by get_current_user dependency
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found. Please complete the onboarding first.")
    
    # Validate that user has completed financial profile
    if not current_user.current_income or not current_user.current_monthly_expenses:
        raise HTTPException(
            status_code=400, 
            detail="Financial profile incomplete. Please complete your income and expense details first."
        )
    
    # Build OneTimeGoalRequest with form data
    goal_request = OneTimeGoalRequest(
        goal_name=goal_name,
        goal_amount=goal_amount,
        years_to_goal=years_to_goal,
        pre_ret_return=pre_ret_return,
        existing_corpus=existing_corpus,
        existing_monthly_sip=existing_monthly_sip,
        risk_tolerance=risk_tolerance
    )
    
    # Calculate goal plan using user's financial profile
    plan = one_time_goal(goal_request, current_user)
    
    # Save plan to database
    try:
        save_one_time_goal_plan(db, current_user.id, plan)
        print(f"✓ One-time goal plan '{goal_name}' saved for user {current_user.id}")
    except Exception as e:
        # Log error but don't fail the response - plan calculation is more important
        print(f"Warning: Failed to save goal plan to database: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return plan

@router.post("/explain_one_time_goal")
def endpoint_explain_one_time_goal(request: ExplainOneTimeGoalRequest):
    return {
        "explanation": explain_one_time_goal_with_ai(
            request.goal_plan,
            request.user_question
        )
    }
