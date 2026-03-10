from __future__ import annotations
from pydantic import BaseModel, Field, model_validator,EmailStr
from typing import Optional

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self
    

class UserBase(BaseModel):
    name: str = Field(..., description="Full name of the user")
    email: EmailStr = Field(..., description="Email address of the user")
    phone_number: str = Field(..., min_length=10, max_length=10, description="Phone number of the user without country code (10 digits)")
    password: str = Field(..., min_length=6, description="Password for the user account (min 6 characters)")
    current_monthly_expenses: float = Field(..., gt=0, description="Current Monthly Household Expenses")
    inflation_rate: float = Field(6.0, gt=0, le=20, description="Expected Inflation Rate (%)")
    

class CreateUser(UserBase):
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
    current_monthly_expenses: Optional[float] = Field(None, gt=0, description="Current Monthly Household Expenses")
    inflation_rate: Optional[float] = Field(None, gt=0, le=20, description="Expected Inflation Rate (%)")

    spouse_age: Optional[int] = Field(None, ge=18, le=80)
    spouse_income: Optional[float] = Field(None, ge=0)
    spouse_income_raise_pct: Optional[float] = Field(None, ge=0, le=50)

    @model_validator(mode='after')
    def validate_spouse_fields(self) -> Self:
        if self.marital_status == "Married":
            if self.spouse_age is None:
                raise ValueError("spouse_age is required when marital_status is 'Married'")
        return self
    
class UserOut(UserBase):
    id: int = Field(..., description="Unique identifier for the user")
    
    class Config:
        form_attributes = True


class Retirement(CreateUser):
    retirement_age: int = Field(..., ge=35, le=80, description="Target Retirement Age")
    post_retirement_expense_pct: float = Field(
        ..., gt=0, le=100,
        description="Post-retirement expenses as % of pre-retirement expenses (e.g. 70 means 70%)"
    )
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

    @property
    def years_to_retirement(self) -> int:
        return self.retirement_age - self.age

    @property
    def retirement_duration(self) -> int:
        return self.life_expectancy - self.retirement_age


class RetirementRequest(BaseModel):
    retirement_age: int = Field(..., ge=35, le=80, description="Target Retirement Age")
    post_retirement_expense_pct: float = Field(..., gt=0, le=100, description="Post-retirement expenses as % of pre-retirement expenses")
    post_retirement_return: float = Field(7.0, gt=0, le=20, description="Expected annual return on retirement corpus post-retirement (%)")
    pre_retirement_return: float = Field(10.0, gt=0, le=20, description="Expected blended annual return on portfolio pre-retirement (%)")
    life_expectancy: int = Field(..., ge=60, le=100, description="Life expectancy of the younger spouse (or self if single)")
    annual_post_retirement_income: float = Field(0.0, ge=0, description="Annual post-retirement income (pension, rent, etc.) in today's value")
    existing_corpus: float = Field(0.0, ge=0, description="Existing retirement corpus today")
    existing_monthly_sip: float = Field(0.0, ge=0, description="Existing monthly SIP toward retirement")
    sip_raise_pct: float = Field(0.0, ge=0, le=50, description="Annual step-up % on existing SIP (0 if no step-up)")

    @model_validator(mode='after')
    def validate_retirement_inputs(self) -> Self:
        if self.life_expectancy <= self.retirement_age:
            raise ValueError("life_expectancy must be greater than retirement_age")
        return self


class BucketAllocation(BaseModel):
    name: str
    size: float
    equity_pct: float
    debt_pct: float
    years_covered: str
    purpose: str
    equity_amount: float
    debt_amount: float
    
class ExplainRetirementRequest(BaseModel):
    retirement_plan: dict
    user_question: Optional[str] = None
    
class ExplainOneTimeGoalRequest(BaseModel):
    goal_plan: dict
    user_question: Optional[str] = None

