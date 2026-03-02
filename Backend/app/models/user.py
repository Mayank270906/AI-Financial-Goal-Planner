from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import Optional

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self


class CreateUser(BaseModel):
    marital_status: str = Field(..., description="'Single' or 'Married'")
    age: int = Field(..., ge=18, le=80, description="Current Age")
    current_income: float = Field(..., gt=0, description="Current Annual Income")
    income_raise_pct: float = Field(..., ge=0, le=50, description="Expected Annual Income Raise (%)")

    spouse_age: Optional[int] = Field(None, ge=18, le=80)
    spouse_income: Optional[float] = Field(None, ge=0)
    spouse_income_raise_pct: Optional[float] = Field(None, ge=0, le=50)

    @model_validator(mode='after')
    def validate_spouse_fields(self) -> Self:
        if self.marital_status == "Married":
            if self.spouse_age is None:
                raise ValueError("spouse_age is required when marital_status is 'Married'")
        return self


class UpdateUser(BaseModel):
    marital_status: Optional[str] = Field(None, description="'Single' or 'Married'")
    age: Optional[int] = Field(None, ge=18, le=80, description="Current Age")
    current_income: Optional[float] = Field(None, gt=0, description="Current Annual Income")
    income_raise_pct: Optional[float] = Field(None, ge=0, le=50, description="Expected Annual Income Raise (%)")

    spouse_age: Optional[int] = Field(None, ge=18, le=80)
    spouse_income: Optional[float] = Field(None, ge=0)
    spouse_income_raise_pct: Optional[float] = Field(None, ge=0, le=50)

    @model_validator(mode='after')
    def validate_spouse_fields(self) -> Self:
        if self.marital_status == "Married":
            if self.spouse_age is None:
                raise ValueError("spouse_age is required when marital_status is 'Married'")
        return self


class Retirement(CreateUser):
    """Retirement goal — inherits user profile fields from CreateUser."""
    retirement_age: int = Field(..., ge=35, le=80, description="Target Retirement Age")
    current_monthly_expenses: float = Field(..., gt=0, description="Current Monthly Household Expenses")
    post_retirement_expense_pct: float = Field(
        ..., gt=0, le=100,
        description="Post-retirement expenses as % of pre-retirement expenses (e.g. 70 means 70%)"
    )
    inflation_rate: float = Field(6.0, gt=0, le=20, description="Expected Inflation Rate (%)")
    post_retirement_return: float = Field(
        7.0, gt=0, le=20,
        description="Expected annual return on retirement corpus post-retirement (%)"
    )
    pre_retirement_return: float = Field(
        10.0, gt=0, le=20,
        description="Expected blended annual return on portfolio pre-retirement (%)"
    )
    life_expectancy: int = Field(
        ..., ge=60, le=100,
        description="Life expectancy of the younger spouse (or self if single)"
    )
    annual_post_retirement_income: float = Field(
        0.0, ge=0,
        description="Annual post-retirement income (pension, rent, etc.) in today's value"
    )
    existing_corpus: float = Field(0.0, ge=0, description="Existing retirement corpus today")
    existing_monthly_sip: float = Field(0.0, ge=0, description="Existing monthly SIP toward retirement")
    sip_raise_pct: float = Field(
        0.0, ge=0, le=50,
        description="Annual step-up % on existing SIP (0 if no step-up)"
    )

    @model_validator(mode='after')
    def validate_retirement_inputs(self) -> Self:
        if self.retirement_age <= self.age:
            raise ValueError("retirement_age must be greater than current age")
        if self.life_expectancy <= self.retirement_age:
            raise ValueError("life_expectancy must be greater than retirement_age")
        if self.sip_raise_pct > self.income_raise_pct:
            raise ValueError(
                f"sip_raise_pct ({self.sip_raise_pct}%) cannot exceed "
                f"income_raise_pct ({self.income_raise_pct}%). "
                f"SIP cannot step up faster than income grows."
            )
        return self

    @property
    def years_to_retirement(self) -> int:
        return self.retirement_age - self.age

    @property
    def retirement_duration(self) -> int:
        return self.life_expectancy - self.retirement_age

class BucketAllocation(BaseModel):
    name: str
    size: float
    equity_pct: float
    debt_pct: float
    years_covered: str
    purpose: str
    equity_amount: float
    debt_amount: float