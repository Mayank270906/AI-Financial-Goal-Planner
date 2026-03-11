from fastapi import APIRouter, Form, Depends, HTTPException
from app.schemas.user import Retirement, ExplainRetirementRequest, ExplainOneTimeGoalRequest
from app.schemas.goals import OneTimeGoalRequest, RecurringGoalRequest
from pydantic import ValidationError
from app.services.math.goals import get_retirement_plan, explain_retirement_plan_with_ai, save_retirement_plan, one_time_goal, explain_one_time_goal_with_ai, save_one_time_goal_plan, compute_recurring_goal, save_recurring_goal_plan
from app.databse import get_db
from app.models.db import User
from app.routes.auth import get_current_user
from app.services.math.conflict_engine import run_and_save_conflict_engine
from sqlalchemy.orm import Session
import json
from app.utils.log_format import JSONFormatter
import logging

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("goals_router")
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)



router = APIRouter(prefix="/goals", tags=["goals"])


def _validation_error_detail(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Validation failed"
    first = errors[0]
    ctx = first.get("ctx") or {}
    return str(ctx.get("error", first.get("msg", "Validation failed")))


# Retirement Planning Endpoint
@router.post("/retirement")
async def endpoint_retirement(
    marital_status: str | None = Form(None, description="'Single' or 'Married'"),
    age: int | None = Form(None, ge=18, le=80, description="Current Age"),
    current_income: float | None = Form(None, gt=0, description="Current Annual Income"),
    income_raise_pct: float | None = Form(None, ge=0, le=50, description="Expected Annual Income Raise (%)"),
    current_monthly_expenses: float | None = Form(None, gt=0, description="Current Monthly Household Expenses"),
    inflation_rate: float | None = Form(None, gt=0, le=20, description="Expected Inflation Rate (%)"),
    spouse_age: int | None = Form(None, ge=18, le=80),
    spouse_income: float | None = Form(None, ge=0),
    spouse_income_raise_pct: float | None = Form(None, ge=0, le=50),
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
    logger.info({
        "event": "retirement_plan_request",
        "user_id": current_user.id if current_user else None,
    })

    # User already fetched from DB by get_current_user dependency
    if not current_user:
        logger.error({
            "event": "retirement_plan_failed",
            "reason": "user_not_found",
            "status_code": 404,
        })
        raise HTTPException(status_code=404, detail="User not found. Please complete the onboarding first.")

    profile_data = {
        "name": current_user.full_name,
        "email": current_user.email,
        "phone_number": current_user.phone_number,
        "password": "placeholder",
        "marital_status": marital_status if marital_status is not None else current_user.marital_status,
        "age": age if age is not None else current_user.age,
        "current_income": current_income if current_income is not None else current_user.current_income,
        "income_raise_pct": income_raise_pct if income_raise_pct is not None else current_user.income_raise_pct,
        "current_monthly_expenses": current_monthly_expenses if current_monthly_expenses is not None else current_user.current_monthly_expenses,
        "inflation_rate": inflation_rate if inflation_rate is not None else current_user.inflation_rate,
        "spouse_age": spouse_age if spouse_age is not None else current_user.spouse_age,
        "spouse_income": spouse_income if spouse_income is not None else current_user.spouse_income,
        "spouse_income_raise_pct": (
            spouse_income_raise_pct if spouse_income_raise_pct is not None else current_user.spouse_income_raise_pct
        ),
    }

    try:
        data = Retirement(
            **profile_data,
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
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc

    override_map = {
        "marital_status": marital_status,
        "age": age,
        "current_income": current_income,
        "income_raise_pct": income_raise_pct,
        "current_monthly_expenses": current_monthly_expenses,
        "inflation_rate": inflation_rate,
        "spouse_age": spouse_age,
        "spouse_income": spouse_income,
        "spouse_income_raise_pct": spouse_income_raise_pct,
    }
    profile_updated = any(value is not None for value in override_map.values())
    if profile_updated:
        current_user.marital_status = data.marital_status
        current_user.age = data.age
        current_user.current_income = data.current_income
        current_user.income_raise_pct = data.income_raise_pct
        current_user.current_monthly_expenses = data.current_monthly_expenses
        current_user.inflation_rate = data.inflation_rate
        current_user.spouse_age = data.spouse_age
        current_user.spouse_income = data.spouse_income
        current_user.spouse_income_raise_pct = data.spouse_income_raise_pct
        db.commit()
        db.refresh(current_user)
    
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
        logger.info({
            "event": "retirement_plan_saved",
            "user_id": current_user.id,
        })
    except Exception as e:
        logger.warning({
            "event": "retirement_plan_save_failed",
            "user_id": current_user.id,
            "error_type": type(e).__name__,
            "error": str(e),
        })
        import traceback
        traceback.print_exc()
        
        
    conflict_results = await run_and_save_conflict_engine(user_id=current_user.id, db=db)
    if conflict_results["overall_status"] == "all_clear":
        logger.info({
            "event": "conflict_engine_completed",
            "user_id": current_user.id,
            "overall_status": "all_clear",
        })
    else:
        logger.warning({
            "event": "conflict_engine_completed",
            "user_id": current_user.id,
            "overall_status": conflict_results.get("overall_status"),
        })

    logger.info({
        "event": "retirement_plan_success",
        "user_id": current_user.id,
        "plan_status": plan.get("status") if isinstance(plan, dict) else None,
    })
    
    return plan

@router.post("/explain_retirement_plan")
def endpoint_explain_retirement_plan(request: ExplainRetirementRequest):
    logger.info({"event": "explain_retirement_plan_request"})
    explanation = explain_retirement_plan_with_ai(
        request.retirement_plan,
        request.user_question
    )
    logger.info({"event": "explain_retirement_plan_success"})
    return {
        "explanation": explanation
    }
    
# One-Time Goal Planning Endpoint

@router.post("/one_time_goal")
async def endpoint_one_time_goal(
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
    logger.info({
        "event": "one_time_goal_request",
        "user_id": current_user.id if current_user else None,
        "goal_name": goal_name,
    })

    # User already fetched from DB by get_current_user dependency
    if not current_user:
        logger.error({
            "event": "one_time_goal_failed",
            "reason": "user_not_found",
            "status_code": 404,
            "goal_name": goal_name,
        })
        raise HTTPException(status_code=404, detail="User not found. Please complete the onboarding first.")
    
    # Validate that user has completed financial profile
    if not current_user.current_income or not current_user.current_monthly_expenses:
        logger.error({
            "event": "one_time_goal_failed",
            "user_id": current_user.id,
            "goal_name": goal_name,
            "reason": "financial_profile_incomplete",
            "status_code": 400,
        })
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
        logger.info({
            "event": "one_time_goal_saved",
            "user_id": current_user.id,
            "goal_name": goal_name,
        })
    except Exception as e:
        logger.warning({
            "event": "one_time_goal_save_failed",
            "user_id": current_user.id,
            "goal_name": goal_name,
            "error_type": type(e).__name__,
            "error": str(e),
        })
        import traceback
        traceback.print_exc()
        
    conflict_results = await run_and_save_conflict_engine(user_id=current_user.id, db=db)
    if conflict_results["overall_status"] == "all_clear":
        logger.info({
            "event": "conflict_engine_completed",
            "user_id": current_user.id,
            "overall_status": "all_clear",
            "goal_name": goal_name,
        })
    else:
        logger.warning({
            "event": "conflict_engine_completed",
            "user_id": current_user.id,
            "overall_status": conflict_results.get("overall_status"),
            "goal_name": goal_name,
        })
    
    logger.info({
        "event": "one_time_goal_success",
        "user_id": current_user.id,
        "goal_name": goal_name,
        "plan_status": plan.get("status") if isinstance(plan, dict) else None,
    })

    
    return plan

@router.post("/explain_one_time_goal")
def endpoint_explain_one_time_goal(request: ExplainOneTimeGoalRequest):
    logger.info({"event": "explain_one_time_goal_request"})
    explanation = explain_one_time_goal_with_ai(
        request.goal_plan,
        request.user_question
    )
    logger.info({"event": "explain_one_time_goal_success"})
    return {
        "explanation": explanation
    }
    
# Recurring Goal Planning Endpoint

@router.post("/recurring_goal")
async def endpoint_recurring_goal(
    goal_name : str = Form(..., description="Name of the goal (e.g., 'Vacation Every 3 years', 'Annual Gadget Upgrade')"),
    current_cost : float = Form(..., gt=0, description="Current cost of the goal in today's value"),
    years_to_first : int = Form(..., ge=0, description="Years until the first occurrence of the goal"),
    frequency_years : int = Form(..., ge=1, description="Frequency of the goal in years (e.g., 3 for every 3 years)"),
    num_occurrences : int = Form(..., ge=1, description="Total number of occurrences of the goal"),
    goal_inflation_pct : float = Form(6.0, gt=0, le=20, description="Expected annual inflation rate for the goal (%)"),
    expected_return_pct : float = Form(10.0, gt=1, le=20, description="Expected annual return on investments (%)"),
    existing_corpus : float = Form(0.0, ge=0, description="Existing savings toward this recurring goal"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ):
    logger.info({
        "event": "recurring_goal_request",
        "user_id": current_user.id if current_user else None,
        "goal_name": goal_name,
    })

    # User already fetched from DB by get_current_user dependency
    if not current_user:
        logger.error({
            "event": "recurring_goal_failed",
            "reason": "user_not_found",
            "status_code": 404,
            "goal_name": goal_name,
        })
        raise HTTPException(status_code=404, detail="User not found. Please complete the onboarding first.")
    
    # Validate that user has completed financial profile
    if not current_user.current_income or not current_user.current_monthly_expenses:
        logger.error({
            "event": "recurring_goal_failed",
            "user_id": current_user.id,
            "goal_name": goal_name,
            "reason": "financial_profile_incomplete",
            "status_code": 400,
        })
        raise HTTPException(
            status_code=400, 
            detail="Financial profile incomplete. Please complete your income and expense details first."
        )
    
    # Validate and construct RecurringGoalRequest
    try:
        data = RecurringGoalRequest(
            goal_name=goal_name,
            current_cost=current_cost,
            years_to_first=years_to_first,
            frequency_years=frequency_years,
            num_occurrences=num_occurrences,
            goal_inflation_pct=goal_inflation_pct,
            expected_return_pct=expected_return_pct,
            income_raise_pct=current_user.income_raise_pct,
            monthly_income=current_user.current_income / 12,
            monthly_expenses=current_user.current_monthly_expenses,
            existing_corpus=existing_corpus
        )
    except ValidationError as e:
        detail = _validation_error_detail(e)
        logger.error({
            "event": "recurring_goal_failed",
            "user_id": current_user.id,
            "goal_name": goal_name,
            "reason": "validation_error",
            "status_code": 422,
            "error": detail,
        })
        raise HTTPException(
            status_code=422,
            detail=detail,
        )
    
    plan = compute_recurring_goal(data)

    try:
        save_recurring_goal_plan(db, current_user.id, plan)
        logger.info({
            "event": "recurring_goal_saved",
            "user_id": current_user.id,
            "goal_name": goal_name,
        })
    except Exception as e:
        logger.warning({
            "event": "recurring_goal_save_failed",
            "user_id": current_user.id,
            "goal_name": goal_name,
            "error_type": type(e).__name__,
            "error": str(e),
        })
        import traceback
        traceback.print_exc()
        
    conflict_results = await run_and_save_conflict_engine(user_id=current_user.id, db=db)
    if conflict_results["overall_status"] == "all_clear":
        logger.info({
            "event": "conflict_engine_completed",
            "user_id": current_user.id,
            "overall_status": "all_clear",
            "goal_name": goal_name,
        })
    else:
        logger.warning({
            "event": "conflict_engine_completed",
            "user_id": current_user.id,
            "overall_status": conflict_results.get("overall_status"),
            "goal_name": goal_name,
        })

    logger.info({
        "event": "recurring_goal_success",
        "user_id": current_user.id,
        "goal_name": goal_name,
        "plan_status": plan.get("status") if isinstance(plan, dict) else None,
    })
    

    return plan

@router.get("/profile_overview")
async def endpoint_profile_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logger.info({
        "event": "profile_overview_request",
        "user_id": current_user.id if current_user else None,
    })

    if not current_user:
        logger.error({
            "event": "profile_overview_failed",
            "reason": "user_not_found",
            "status_code": 404,
        })
        raise HTTPException(status_code=404, detail="User not found. Please complete the onboarding first.")
    
    results= await run_and_save_conflict_engine(user_id=current_user.id, db=db)
    logger.info({
        "event": "profile_overview_success",
        "user_id": current_user.id,
        "overall_status": results.get("overall_status"),
    })

    return results