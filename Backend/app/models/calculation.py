from pydantic import BaseModel, Field
from typing import Optional, Dict

class FutureValue(BaseModel):
    principal: float
    infation_rate: float
    years: float
    
class BlendedReturn(BaseModel):
    equity_pct: float
    debt_pct: float
    return_equity: float
    return_debt: float
    
class RequiredAnnualSavings(BaseModel):
    future_value: float
    return_rate: float
    years: float
    current_savings: Optional[float] = 0
    
class SuggestedAllocation(BaseModel):
    years: float
    risk : str
    
class CheckFeasibility(BaseModel):
    annual_saving_required: float
    max_possible_saving: float
    
class CheckRebalancing(BaseModel):
    planned_alloc: dict
    current_alloc: dict
    threshold: float = 0.5

class SIPRequest(BaseModel):
    target_corpus: float
    pre_ret_return: float
    annual_step_up_percent: float
    years_to_goal: int

class GlidePathRequest(BaseModel):
    current_age: int
    goal_age: int
    start_equity_percent: float
    end_equity_percent: float

class RebalanceRequest(BaseModel):
    current_equity_value: float
    current_debt_value: float
    current_year_target_ratio: float  # e.g., 0.60 for 60% equity
