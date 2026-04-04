use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Json, Response},
};
use ethers::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::AppState;

// ──────────────────────────────────────────────
// Request / Response types
// ──────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct MintRequest {
    pub user_wallet: String,
    pub plan_hash: String,
    #[allow(dead_code)]
    pub timestamp: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateRequest {
    pub user_wallet: String,
    pub new_hash: String,
    #[allow(dead_code)]
    pub timestamp: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct MintResponse {
    pub success: bool,
    pub tx_hash: String,
    pub block_number: u64,
    pub token_id: u64,
    pub etherscan: String,
}

#[derive(Debug, Serialize)]
pub struct UpdateResponse {
    pub success: bool,
    pub tx_hash: String,
    pub new_version: u16,
}

#[derive(Debug, Serialize)]
pub struct PassportResponse {
    pub wallet: String,
    pub plan_hash: String,
    pub timestamp: u64,
    pub version: u16,
    pub is_valid: bool,
    pub etherscan: String,
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

fn parse_bytes32(hex_str: &str) -> Result<[u8; 32], String> {
    let clean = hex_str.strip_prefix("0x").unwrap_or(hex_str);
    if clean.len() != 64 {
        return Err(format!(
            "Invalid hash length: expected 64 hex chars, got {}",
            clean.len()
        ));
    }
    let bytes = hex::decode(clean).map_err(|e| format!("Invalid hex: {}", e))?;
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&bytes);
    Ok(arr)
}

fn parse_address(addr_str: &str) -> Result<Address, String> {
    addr_str
        .parse::<Address>()
        .map_err(|e| format!("Invalid address '{}': {}", addr_str, e))
}

fn error_response(status: StatusCode, msg: impl ToString) -> Response {
    (status, Json(json!({ "success": false, "error": msg.to_string() }))).into_response()
}

// ──────────────────────────────────────────────
// POST /chain/passport/mint
// ──────────────────────────────────────────────

pub async fn mint_passport(
    State(state): State<Arc<AppState>>,
    Json(req): Json<MintRequest>,
) -> Response {
    let user_wallet = match parse_address(&req.user_wallet) {
        Ok(addr) => addr,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let plan_hash = match parse_bytes32(&req.plan_hash) {
        Ok(h) => h,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let contract = &state.passport_contract;
    let call = contract.mint(user_wallet, plan_hash);

    // Estimate gas first
    if let Err(e) = call.estimate_gas().await {
        return error_response(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Gas estimation failed: {}", e),
        );
    }

    // Send transaction and await receipt in separate steps to avoid lifetime issues
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
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                "Transaction dropped or not confirmed",
            );
        }
        Err(e) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Transaction failed: {}", e),
            );
        }
    };

    let tx_hash = format!("{:#x}", receipt.transaction_hash);
    let block_number = receipt.block_number.map(|b| b.as_u64()).unwrap_or(0);

    let token_id = match contract.token_ids(user_wallet).call().await {
        Ok(id) => id.as_u64(),
        Err(_) => 0,
    };

    let etherscan = format!("{}/tx/{}", state.config.etherscan_base_url, tx_hash);

    (
        StatusCode::OK,
        Json(json!(MintResponse {
            success: true,
            tx_hash,
            block_number,
            token_id,
            etherscan,
        })),
    )
        .into_response()
}

// ──────────────────────────────────────────────
// POST /chain/passport/update
// ──────────────────────────────────────────────

pub async fn update_passport(
    State(state): State<Arc<AppState>>,
    Json(req): Json<UpdateRequest>,
) -> Response {
    let user_wallet = match parse_address(&req.user_wallet) {
        Ok(addr) => addr,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let new_hash = match parse_bytes32(&req.new_hash) {
        Ok(h) => h,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let contract = &state.passport_contract;
    let call = contract.update_hash(user_wallet, new_hash);

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

    let new_version = match contract.get_passport(user_wallet).call().await {
        Ok((_, _, version, _)) => version,
        Err(_) => 0,
    };

    (
        StatusCode::OK,
        Json(json!(UpdateResponse {
            success: true,
            tx_hash,
            new_version,
        })),
    )
        .into_response()
}

// ──────────────────────────────────────────────
// GET /chain/passport/:wallet
// ──────────────────────────────────────────────

pub async fn get_passport(
    State(state): State<Arc<AppState>>,
    Path(wallet): Path<String>,
) -> Response {
    let user_wallet = match parse_address(&wallet) {
        Ok(addr) => addr,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let contract = &state.passport_contract;

    match contract.get_passport(user_wallet).call().await {
        Ok((plan_hash, timestamp, version, is_valid)) => {
            let etherscan = format!(
                "{}/address/{:#x}",
                state.config.etherscan_base_url, user_wallet
            );

            (
                StatusCode::OK,
                Json(json!(PassportResponse {
                    wallet: format!("{:#x}", user_wallet),
                    plan_hash: format!("0x{}", hex::encode(plan_hash)),
                    timestamp: timestamp.as_u64(),
                    version,
                    is_valid,
                    etherscan,
                })),
            )
                .into_response()
        }
        Err(e) => error_response(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read passport: {}", e),
        ),
    }
}
