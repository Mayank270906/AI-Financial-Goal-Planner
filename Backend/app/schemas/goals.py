from pydantic import BaseModel, Field, model_validator
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
    goal_name:          str
    current_cost:       float = Field(..., gt=0)

    # Timing
    years_to_first:     int   = Field(..., ge=0)
    frequency_years:    int   = Field(..., ge=1)   # every N years
    num_occurrences:    int   = Field(..., ge=1)

    # Assumptions
    goal_inflation_pct: float = Field(default=6.0, ge=0, le=20)
    expected_return_pct:float = Field(default=10.0, ge=1, le=20)

    # From user DB profile
    income_raise_pct:   float
    monthly_income:     float
    monthly_expenses:   float
    existing_corpus:    float = 0.0

    @model_validator(mode="after")
    def validate(self):
        if self.monthly_expenses > self.monthly_income:
            raise ValueError(
                f"Monthly expenses (${self.monthly_expenses:.2f}) cannot exceed monthly income (${self.monthly_income:.2f})"
            )
        return self