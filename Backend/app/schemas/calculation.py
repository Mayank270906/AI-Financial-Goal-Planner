from pydantic import BaseModel, Field, model_validator
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
    

class CheckFeasibilityRequest(BaseModel):
    # From SIP calculator output
    starting_monthly_sip:  float          # output of calculate_sip()
    annual_step_up_pct:    float          # output of calculate_sip() — derived g

    # User's financial profile (pulled from DB after auth)
    monthly_income:        float          # current monthly take-home
    income_raise_pct:      float          # annual salary hike %
    monthly_expenses:      float          # current fixed monthly expenses
    years_to_goal:         int

    # Optional: other existing SIP commitments (retirement, other goals)
    existing_monthly_sip:  float = 0.0   # already committed SIPs

    # Savings cap — default 50% of disposable income
    savings_cap_pct:       float = Field(default=50.0, ge=10, le=90)

    @model_validator(mode="after")
    def validate(self):
        if self.monthly_income <= 0:
            raise ValueError("monthly_income must be positive")
        if self.monthly_expenses >= self.monthly_income:
            raise ValueError("monthly_expenses cannot exceed monthly_income")
        return self

    
class CheckRebalancing(BaseModel):
    planned_alloc: dict
    current_alloc: dict
    threshold: float = 0.5

class SIPRequest(BaseModel):
    goal_amount: float
    years_to_goal: float
    pre_ret_return: float
    inflation_rate: float
    income_raise_pct: float

class GlidePathRequest(BaseModel):
    current_age:          int
    goal_age:             int
    start_equity_percent: float = Field(..., ge=0, le=100)
    end_equity_percent:   float = Field(..., ge=0, le=100)

    @model_validator(mode="after")
    def validate_inputs(self):
        if self.goal_age <= self.current_age:
            raise ValueError("goal_age must be greater than current_age")
        if self.start_equity_percent < self.end_equity_percent:
            raise ValueError(
                "start_equity_percent must be greater than or equal to "
                "end_equity_percent — a glide path reduces equity over time"
            )
        return self

class RebalanceRequest(BaseModel):
    current_equity_value: float
    current_debt_value: float
    current_year_target_ratio: float  
