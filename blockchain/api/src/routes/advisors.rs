use std::sync::Arc;

use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Json, Response},
};
use ethers::prelude::*;
use serde::Deserialize;
use serde_json::json;

use crate::AppState;
use crate::middleware::auth::verify_admin_key;

// ──────────────────────────────────────────────
// Request types
// ──────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct RegisterAdvisorRequest {
    pub wallet: String,
    pub sebi_number: String,
    pub name: String,
    pub email: String,
    pub phone: String,
    pub years_experience: i32,
}

#[derive(Debug, Deserialize)]
pub struct VerifyAdvisorRequest {
    pub wallet: String,
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

fn parse_address(addr_str: &str) -> Result<Address, String> {
    addr_str
        .parse::<Address>()
        .map_err(|e| format!("Invalid address '{}': {}", addr_str, e))
}

fn error_response(status: StatusCode, msg: impl ToString) -> Response {
    (status, Json(json!({ "success": false, "error": msg.to_string() }))).into_response()
}

// ──────────────────────────────────────────────
// POST /chain/advisors/register
// ──────────────────────────────────────────────

pub async fn register_advisor(
    State(state): State<Arc<AppState>>,
    Json(req): Json<RegisterAdvisorRequest>,
) -> Response {
    let wallet = match parse_address(&req.wallet) {
        Ok(addr) => addr,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let contract = &state.advisor_contract;
    let call = contract.register_advisor(wallet, req.sebi_number.clone());

    if let Err(e) = call.estimate_gas().await {
        return error_response(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Gas estimation failed: {}", e),
        );
    }

    let pending_tx = match call.send().await {
        Ok(tx) => tx,
        Err(e) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to send transaction: {}", e),
            );
        }
    };

    let receipt = match pending_tx.confirmations(1).await {
        Ok(Some(r)) => r,
        Ok(None) => {
            return error_response(StatusCode::INTERNAL_SERVER_ERROR, "Transaction not confirmed");
        }
        Err(e) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Transaction failed: {}", e),
            );
        }
    };

    let tx_hash = format!("{:#x}", receipt.transaction_hash);
    let etherscan = format!("{}/tx/{}", state.config.etherscan_base_url, tx_hash);

    let query = r#"
        INSERT INTO ca_profiles (wallet, name, email, phone, years_experience)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (wallet) DO UPDATE SET
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            phone = EXCLUDED.phone,
            years_experience = EXCLUDED.years_experience
    "#;

    if let Err(e) = sqlx::query(query)
        .bind(&req.wallet)
        .bind(&req.name)
        .bind(&req.email)
        .bind(&req.phone)
        .bind(req.years_experience)
        .execute(&state.db_pool)
        .await
    {
        return error_response(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Database insert failed: {}", e),
        );
    }

    (
        StatusCode::OK,
        Json(json!({
            "success": true,
            "tx_hash": tx_hash,
            "wallet": req.wallet,
            "sebi_number": req.sebi_number,
            "name": req.name,
            "email": req.email,
            "phone": req.phone,
            "years_experience": req.years_experience,
            "etherscan": etherscan,
        })),
    )
        .into_response()
}

// ──────────────────────────────────────────────
// POST /chain/advisors/verify
// ──────────────────────────────────────────────

pub async fn verify_advisor(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(req): Json<VerifyAdvisorRequest>,
) -> Response {
    // Verify admin key
    let auth_header = headers
        .get("X-Admin-Key")
        .and_then(|v| v.to_str().ok())
        .or_else(|| {
            headers
                .get("Authorization")
                .and_then(|v| v.to_str().ok())
        });

    if let Err(resp) = verify_admin_key(auth_header, &state.config) {
        return resp;
    }

    let wallet = match parse_address(&req.wallet) {
        Ok(addr) => addr,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let contract = &state.advisor_contract;
    let call = contract.verify_advisor(wallet);

    if let Err(e) = call.estimate_gas().await {
        return error_response(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Gas estimation failed: {}", e),
        );
    }

    let pending_tx = match call.send().await {
        Ok(tx) => tx,
        Err(e) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to send transaction: {}", e),
            );
        }
    };

    let receipt = match pending_tx.confirmations(1).await {
        Ok(Some(r)) => r,
        Ok(None) => {
            return error_response(StatusCode::INTERNAL_SERVER_ERROR, "Transaction not confirmed");
        }
        Err(e) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Transaction failed: {}", e),
            );
        }
    };

    let tx_hash = format!("{:#x}", receipt.transaction_hash);
    let etherscan = format!("{}/tx/{}", state.config.etherscan_base_url, tx_hash);

    let wallet_str = format!("{:#x}", wallet);
    let profile = sqlx::query_as::<_, CaProfile>("SELECT * FROM ca_profiles WHERE wallet ILIKE $1")
        .bind(&wallet_str)
        .fetch_optional(&state.db_pool)
        .await
        .unwrap_or(None);

    (
        StatusCode::OK,
        Json(json!({
            "success": true,
            "tx_hash": tx_hash,
            "wallet": req.wallet,
            "verified": true,
            "name": profile.as_ref().and_then(|p| p.name.clone()),
            "email": profile.as_ref().and_then(|p| p.email.clone()),
            "phone": profile.as_ref().and_then(|p| p.phone.clone()),
            "years_experience": profile.as_ref().and_then(|p| p.years_experience),
            "etherscan": etherscan,
        })),
    )
        .into_response()
}

#[derive(sqlx::FromRow)]
struct CaProfile {
    wallet: String,
    name: Option<String>,
    email: Option<String>,
    phone: Option<String>,
    years_experience: Option<i32>,
}

// ──────────────────────────────────────────────
// GET /chain/advisors/list
// ──────────────────────────────────────────────

pub async fn list_advisors(
    State(state): State<Arc<AppState>>,
) -> Response {
    let contract = &state.advisor_contract;

    let db_profiles = match sqlx::query_as::<_, CaProfile>("SELECT * FROM ca_profiles")
        .fetch_all(&state.db_pool)
        .await
    {
        Ok(profiles) => profiles,
        Err(e) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to read profiles from DB: {}", e),
            )
        }
    };

    match contract.get_advisors().call().await {
        Ok(advisors) => {
            let serialized: Vec<serde_json::Value> = advisors
                .iter()
                .map(|a| {
                    let wallet_str = format!("{:#x}", a.wallet);
                    
                    // Match with DB profile
                    let profile = db_profiles
                        .iter()
                        .find(|p| p.wallet.eq_ignore_ascii_case(&wallet_str));

                    json!({
                        "wallet": wallet_str,
                        "sebi_number": a.sebi_number,
                        "is_verified": a.is_verified,
                        "registered_at": a.registered_at.as_u64(),
                        "name": profile.and_then(|p| p.name.clone()),
                        "email": profile.and_then(|p| p.email.clone()),
                        "phone": profile.and_then(|p| p.phone.clone()),
                        "years_experience": profile.and_then(|p| p.years_experience),
                    })
                })
                .collect();

            (
                StatusCode::OK,
                Json(json!({
                    "advisor_count": serialized.len(),
                    "advisors": serialized,
                })),
            )
                .into_response()
        }
        Err(e) => error_response(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read advisors: {}", e),
        ),
    }
}
