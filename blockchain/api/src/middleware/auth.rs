use axum::{
    extract::Request,
    http::StatusCode,
    middleware::Next,
    response::{IntoResponse, Json, Response},
};
use serde_json::json;

use crate::config::Config;

/// Middleware that verifies the `Authorization: Bearer <key>` header
/// against the `GOALPATH_INTERNAL_KEY` environment variable.
/// The /chain/health endpoint is excluded from this check.
pub async fn auth_middleware(
    request: Request,
    next: Next,
) -> Response {
    // Skip auth for health check
    if request.uri().path() == "/chain/health" {
        return next.run(request).await;
    }

    // Extract config from extensions
    let config = request
        .extensions()
        .get::<Config>()
        .cloned();

    let config = match config {
        Some(c) => c,
        None => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({ "success": false, "error": "Server configuration error" })),
            )
                .into_response();
        }
    };

    // Check Authorization header
    let auth_header = request
        .headers()
        .get("Authorization")
        .and_then(|v| v.to_str().ok());

    match auth_header {
        Some(header) if header.starts_with("Bearer ") => {
            let token = &header[7..];
            if token == config.goalpath_internal_key || token == config.admin_key {
                next.run(request).await
            } else {
                (
                    StatusCode::UNAUTHORIZED,
                    Json(json!({ "success": false, "error": "Invalid API key" })),
                )
                    .into_response()
            }
        }
        _ => (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "success": false, "error": "Missing or malformed Authorization header. Expected: Bearer <API_KEY>" })),
        )
            .into_response(),
    }
}

/// Verify that a request carries the ADMIN_KEY for admin-only actions.
pub fn verify_admin_key(auth_header: Option<&str>, config: &Config) -> Result<(), Response> {
    match auth_header {
        Some(header) if header.starts_with("Bearer ") => {
            let token = &header[7..];
            if token == config.admin_key {
                Ok(())
            } else {
                Err((
                    StatusCode::UNAUTHORIZED,
                    Json(json!({ "success": false, "error": "Invalid admin key" })),
                )
                    .into_response())
            }
        }
        _ => Err((
            StatusCode::UNAUTHORIZED,
            Json(json!({ "success": false, "error": "Admin authorization required" })),
        )
            .into_response()),
    }
}
