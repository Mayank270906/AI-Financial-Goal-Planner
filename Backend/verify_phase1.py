
import sys
import os

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.getcwd())

from app.models.calculation import (
    CorpusRequest,
    SIPRequest,
    GlidePathRequest,
    RebalanceRequest
)
from app.services.math.calculation import (
    calculate_corpus,
    calculate_sip,
    calculate_glide_path,
    check_portfolio_rebalance
)

def run_tests():
    print("Running Phase 1 Verification Tests...\n")

    # 1. Test Corpus Calculation
    print("1. Testing Corpus Calculation (Endpoint: /calc/corpus)")
    # Scenario: Monthly Exp 50k, Inflation 6%, 20 years to goal, 20 years withdrawal, 8% post-ret return
    # FV Exp = 50000 * (1.06)^20 ~= 160356.77
    # Real Rate = (1.08/1.06) - 1 ~= 0.0188679
    # Corpus = PV of Annuity Due
    corpus_req = CorpusRequest(
        monthly_exp=50000,
        inflation=6.0,
        years_to_goal=20,
        years_in_withdrawal=20,
        post_ret_return=8.0
    )
    corpus_res = calculate_corpus(corpus_req)
    print(f"Input: {corpus_req}")
    print(f"Result: {corpus_res}")
    print("-" * 30)

    # 2. Test SIP Calculation
    print("2. Testing SIP Calculation (Endpoint: /calc/starting-sip)")
    # Scenario: Target 5 Cr (50,000,000), 12% return, 10% step-up, 20 years
    sip_req = SIPRequest(
        target_corpus=50000000,
        pre_ret_return=12.0,
        annual_step_up_percent=10.0,
        years_to_goal=20
    )
    sip_res = calculate_sip(sip_req)
    print(f"Input: {sip_req}")
    print(f"Result: {sip_res}")
    print("-" * 30)

    # 3. Test Glide Path
    print("3. Testing Glide Path (Endpoint: /calc/glide-path)")
    # Scenario: Age 30 to 60. Equity 90% -> 30%.
    # Should see linear decrease over 30 years.
    glide_req = GlidePathRequest(
        current_age=30,
        goal_age=60,
        start_equity_percent=90.0,
        end_equity_percent=30.0
    )
    glide_res = calculate_glide_path(glide_req)
    print(f"Input: {glide_req}")
    # Print first few and last few entries to verifying
    table = glide_res['yearly_allocation_table']
    print(f"First Year: {table[0]}")
    print(f"Mid Year: {table[15]}")
    print(f"Last Year: {table[-1]}")
    print("-" * 30)

    # 4. Test Rebalance Check (5/25 Rule)
    print("4. Testing Rebalance Check (Endpoint: /portfolio/check-rebalance)")
    
    # Case A: Large Domain (Target > 20%), Small Drift (< 5%) -> No Rebalance
    # Target Equity 60%, Actual 63% (Drift 3%)
    rebal_req_a = RebalanceRequest(
        current_equity_value=63000,
        current_debt_value=37000,
        current_year_target_ratio=0.60
    )
    res_a = check_portfolio_rebalance(rebal_req_a)
    print(f"Case A (No Rebalance Expected): {res_a}")

    # Case B: Large Domain (Target > 20%), Large Drift (> 5%) -> Rebalance
    # Target Equity 60%, Actual 66% (Drift 6%)
    rebal_req_b = RebalanceRequest(
        current_equity_value=66000,
        current_debt_value=34000,
        current_year_target_ratio=0.60
    )
    res_b = check_portfolio_rebalance(rebal_req_b)
    print(f"Case B (Rebalance Expected): {res_b}")

    # Case C: Small Domain (Target < 20%), Relative Drift Check
    # Target Equity 10%, Actual 15% (Drift 5% absolute, but 50% relative) -> Rebalance
    rebal_req_c = RebalanceRequest(
        current_equity_value=15000,
        current_debt_value=85000,
        current_year_target_ratio=0.10
    )
    res_c = check_portfolio_rebalance(rebal_req_c)
    print(f"Case C (Rebalance Expected - Small Domain): {res_c}")
    print("-" * 30)

if __name__ == "__main__":
    run_tests()
