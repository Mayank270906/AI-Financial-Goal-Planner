from pydantic import BaseModel, Field, model_validator,EmailStr
from typing import Optional

class OneTimeGoalRequest(BaseModel):
    goal_name: str = Field(..., description="Name of the goal (e.g., 'Buy a Car', 'Home Down Payment')")
    goal_amount: float = Field(..., gt=0, description="Goal amount in today's value")
    years_to_goal: float = Field(..., gt=0, le=50, description="Years until goal")
    pre_ret_return: float = Field(10.0, gt=0, le=20, description="Expected annual return (%)")
    existing_corpus: float = Field(0.0, ge=0, description="Existing savings toward this goal")
    existing_monthly_sip: float = Field(0.0, ge=0, description="Existing monthly SIP for this goal")
    risk_tolerance: str = Field("moderate", description="Risk tolerance: low, moderate, high")
    
class RecurringGoalRequest(BaseModel):
    goal_amount: float
    years_to_goal: float
    pre_ret_return: float
    inflation_rate: float
    income_raise_pct: float