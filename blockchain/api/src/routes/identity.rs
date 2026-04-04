use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Json},
};
use ethers::prelude::*;
use serde_json::json;

use crate::AppState;

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

fn parse_address(addr_str: &str) -> Result<Address, String> {
    addr_str
        .parse::<Address>()
        .map_err(|e| format!("Invalid address '{}': {}", addr_str, e))
}

// ──────────────────────────────────────────────
// GET /chain/identity/:user_wallet
// ──────────────────────────────────────────────

/// Combined view: passport data + token_id — the full Financial Identity Card.
pub async fn get_identity(
    State(state): State<Arc<AppState>>,
    Path(wallet): Path<String>,
) -> impl IntoResponse {
    let user_wallet = match parse_address(&wallet) {
        Ok(addr) => addr,
        Err(e) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({ "success": false, "error": e })),
            )
                .into_response();
        }
    };

    let contract = &state.passport_contract;

    // Fetch passport data
    let passport_result = contract.get_passport(user_wallet).call().await;
    let token_id_result = contract.token_ids(user_wallet).call().await;

    match (passport_result, token_id_result) {
        (Ok((plan_hash, timestamp, version, is_valid)), Ok(token_id)) => {
            let etherscan = format!(
                "{}/address/{:#x}",
                state.config.etherscan_base_url, user_wallet
            );

            (
                StatusCode::OK,
                Json(json!({
                    "wallet": format!("{:#x}", user_wallet),
                    "plan_hash": format!("0x{}", hex::encode(plan_hash)),
                    "timestamp": timestamp.as_u64(),
                    "version": version,
                    "is_valid": is_valid,
                    "token_id": token_id.as_u64(),
                    "contract_address": state.config.passport_contract_address,
                    "network": "Sepolia",
                    "chain_id": state.config.chain_id,
                    "etherscan": etherscan,
                })),
            )
                .into_response()
        }
        (Err(e), _) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "success": false, "error": format!("Failed to read passport: {}", e) })),
        )
            .into_response(),
        (_, Err(e)) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "success": false, "error": format!("Failed to read token ID: {}", e) })),
        )
            .into_response(),
    }
}
