use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Json, Response},
};
use ethers::prelude::*;
use serde::Deserialize;
use serde_json::json;

use crate::AppState;
use crate::contracts::advisor::EngagementEvent;

// ──────────────────────────────────────────────
// Request types
// ──────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct LogEventRequest {
    pub event_type: u8,
    pub plan_id: String,
    pub primary_hash: String,
    #[serde(default)]
    pub secondary_hash: Option<String>,
    pub user_wallet: String,
    pub advisor_wallet: String,
    #[serde(default)]
    pub fee_amount: Option<String>,
    #[serde(default)]
    pub duration_days: Option<u8>,
    #[serde(default)]
    pub service_scope: Option<String>,
    #[serde(default)]
    pub outcome: Option<String>,
    #[serde(default)]
    pub fee_released: Option<bool>,
    #[serde(default)]
    pub timestamp: Option<u64>,
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
// POST /chain/events/log
// ──────────────────────────────────────────────

pub async fn log_event(
    State(state): State<Arc<AppState>>,
    Json(req): Json<LogEventRequest>,
) -> Response {
    if req.event_type > 5 {
        return error_response(StatusCode::BAD_REQUEST, "event_type must be 0-5");
    }

    let user_wallet = match parse_address(&req.user_wallet) {
        Ok(addr) => addr,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let advisor_wallet = match parse_address(&req.advisor_wallet) {
        Ok(addr) => addr,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let primary_hash = match parse_bytes32(&req.primary_hash) {
        Ok(h) => h,
        Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
    };

    let secondary_hash = match &req.secondary_hash {
        Some(h) if !h.is_empty() => match parse_bytes32(h) {
            Ok(h) => h,
            Err(e) => return error_response(StatusCode::BAD_REQUEST, e),
        },
        _ => [0u8; 32],
    };

    let fee_amount: U256 = req
        .fee_amount
        .as_deref()
        .unwrap_or("0")
        .parse()
        .unwrap_or(U256::zero());

    let timestamp = U256::from(
        req.timestamp.unwrap_or(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
        ),
    );

    let evt = EngagementEvent {
        event_type: req.event_type,
        plan_id: req.plan_id.clone(),
        primary_hash,
        secondary_hash,
        user_wallet,
        advisor_wallet,
        fee_amount,
        duration_days: req.duration_days.unwrap_or(0),
        service_scope: req.service_scope.clone().unwrap_or_default(),
        outcome: req.outcome.clone().unwrap_or_default(),
        fee_released: req.fee_released.unwrap_or(false),
        timestamp,
    };

    let contract = &state.advisor_contract;
    let call = contract.log_event(evt);

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
    let block_number = receipt.block_number.map(|b| b.as_u64()).unwrap_or(0);
    let etherscan = format!("{}/tx/{}", state.config.etherscan_base_url, tx_hash);

    (
        StatusCode::OK,
        Json(json!({
            "success": true,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "plan_id": req.plan_id,
            "event_type": req.event_type,
            "etherscan": etherscan,
        })),
    )
        .into_response()
}

// ──────────────────────────────────────────────
// GET /chain/events/:plan_id
// ──────────────────────────────────────────────

pub async fn get_events(
    State(state): State<Arc<AppState>>,
    Path(plan_id): Path<String>,
) -> Response {
    let contract = &state.advisor_contract;

    match contract.get_events(plan_id.clone()).call().await {
        Ok(events) => {
            let serialized: Vec<serde_json::Value> = events
                .iter()
                .map(|evt| {
                    json!({
                        "event_type": evt.event_type,
                        "event_type_name": match evt.event_type {
                            0 => "AGREEMENT_CREATED",
                            1 => "PLAN_SHARED",
                            2 => "ADVISOR_RECOMMENDATION",
                            3 => "USER_APPROVAL",
                            4 => "PLAN_UPDATED_AFTER_ADVICE",
                            5 => "ENGAGEMENT_CLOSED",
                            _ => "UNKNOWN",
                        },
                        "plan_id": evt.plan_id,
                        "primary_hash": format!("0x{}", hex::encode(evt.primary_hash)),
                        "secondary_hash": format!("0x{}", hex::encode(evt.secondary_hash)),
                        "user_wallet": format!("{:#x}", evt.user_wallet),
                        "advisor_wallet": format!("{:#x}", evt.advisor_wallet),
                        "fee_amount": evt.fee_amount.to_string(),
                        "duration_days": evt.duration_days,
                        "service_scope": evt.service_scope,
                        "outcome": evt.outcome,
                        "fee_released": evt.fee_released,
                        "timestamp": evt.timestamp.as_u64(),
                    })
                })
                .collect();

            (
                StatusCode::OK,
                Json(json!({
                    "plan_id": plan_id,
                    "event_count": serialized.len(),
                    "events": serialized,
                })),
            )
                .into_response()
        }
        Err(e) => error_response(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to read events: {}", e),
        ),
    }
}
