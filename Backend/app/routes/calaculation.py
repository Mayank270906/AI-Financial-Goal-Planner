from fastapi import FastAPI, HTTPException, APIRouter, Form
from app.schemas.calculation import (
    FutureValue,
    BlendedReturn,
    RequiredAnnualSavings,
    SuggestedAllocation,
    CheckFeasibilityRequest,
    CheckRebalancing,
    SIPRequest,
    GlidePathRequest,
    RebalanceRequest
)
from app.services.math.calculation import (
    future_value_goal,
    blended_return,
    required_annual_saving, 
    suggest_allocation,
    check_feasibility,
    check_rebalancing,
    calculate_sip,
    calculate_glide_path,
    check_portfolio_rebalance
)

router = APIRouter(prefix="/calculation", tags=["calculation"])

@router.get("/")
def read_root():
    return {"Message": "Financial Calculation API root"}

# --- Existing Endpoints (Preserved) ---

@router.post("/future_value_goal")
def calaculate_future_value(data: FutureValue):
    return future_value_goal(data)

@router.post("/blended_return")
def calaculate_blended_return(data: BlendedReturn):
    return blended_return(data)

@router.post("/required_annual_saving")
def calculate_required_annual_savig(
    future_value: float = Form(),
    return_rate: float = Form(),
    years: float = Form(),
    current_savings: float = Form(0)
):
    data = RequiredAnnualSavings(
        future_value=future_value,
        return_rate=return_rate,
        years=years,
        current_savings=current_savings
    )
    return required_annual_saving(data)

@router.post("/suggest_allocation")
def calculate_suggested_allocation(data: SuggestedAllocation):
    return suggest_allocation(data)

@router.post("/check_feasibility")
def calculate_feasibility(data: CheckFeasibilityRequest):
    return check_feasibility(data)

@router.post("/check_rebalancing")
def calculate_rebalancing(data: CheckRebalancing):
    return check_rebalancing(data)


# --- Phase 1 New Endpoints ---

@router.post("/starting-sip")
def endpoint_calculate_sip(data: SIPRequest):
    return calculate_sip(data)

@router.post("/glide-path")
def endpoint_calculate_glide_path(data: GlidePathRequest):
    return calculate_glide_path(data)

@router.post("/drift")
def endpoint_check_portfolio_rebalance(data: RebalanceRequest):
    return check_portfolio_rebalance(data)