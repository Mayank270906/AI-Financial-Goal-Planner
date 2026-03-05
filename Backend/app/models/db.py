from datetime import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.databse import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Auth fields
    email           = Column(String(255), unique=True, nullable=False, index=True)
    phone_number    = Column(String(20), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_verified     = Column(Boolean, default=False)
    is_active       = Column(Boolean, default=True)

    # Basic profile
    full_name           = Column(String(255), nullable=False)
    age                 = Column(Integer, nullable=True)
    marital_status      = Column(String(20), nullable=True)   # Single / Married

    # Financial profile — maps directly to your Retirement model
    current_income              = Column(Float, nullable=True)
    income_raise_pct            = Column(Float, nullable=True)
    current_monthly_expenses    = Column(Float, nullable=True)
    spouse_age                  = Column(Integer, nullable=True)
    spouse_income               = Column(Float, nullable=True)
    spouse_income_raise_pct     = Column(Float, nullable=True)

    # Plan assumptions — user-adjustable, have defaults
    inflation_rate              = Column(Float, default=6.0)
    pre_retirement_return       = Column(Float, default=10.0)
    post_retirement_return      = Column(Float, default=7.0)

    # Onboarding state
    onboarding_complete = Column(Boolean, default=False)
    onboarding_step     = Column(Integer, default=0)


class RetirementPlan(Base):
    __tablename__ = "retirement_plans"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String(36), nullable=False, index=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    # Full plan output stored as JSON string
    # matches your existing get_retirement_plan() output exactly
    plan_data   = Column(Text, nullable=False)

    # Quick-access fields for list views without parsing JSON
    corpus_required         = Column(Float, nullable=True)
    monthly_sip_required    = Column(Float, nullable=True)
    retirement_age          = Column(Integer, nullable=True)
    status                  = Column(String(20), nullable=True)  # feasible / infeasible
    plan_version            = Column(Integer, default=1)
    is_active               = Column(Boolean, default=True)


class GoalPlan(Base):
    __tablename__ = "goal_plans"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String(36), nullable=False, index=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    
    goal_type   = Column(String(50), nullable=False)   # one_time / recurring
    goal_name   = Column(String(255), nullable=False)
    
    # Financial summary fields (quick access for dashboard)
    target_amount        = Column(Float, nullable=True) # How much is needed in today's terms
    future_value         = Column(Float, nullable=True) # How much will be needed after inflation
    monthly_sip_required = Column(Float, nullable=True) # Required monthly investment
    time_horizon_years   = Column(Integer, nullable=True) # Years from now until goal
    status               = Column(String(20), nullable=True)  # feasible / infeasible
    
    # Detailed JSON output (year-by-year etc)
    goal_data   = Column(Text, nullable=False)      
    
    priority    = Column(Integer, nullable=True)
    is_active   = Column(Boolean, default=True)