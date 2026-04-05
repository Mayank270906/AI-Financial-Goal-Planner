use std::sync::Arc;
use std::str::FromStr;
use axum::{
    extract::State,
    http::StatusCode,
    middleware as axum_middleware,
    response::{IntoResponse, Json},
    routing::{get, post},
    Router,
};
use ethers::prelude::*;
use serde_json::json;
use tower_http::cors::{Any, CorsLayer};
use tracing_subscriber::EnvFilter;

mod config;
mod contracts;
mod middleware;
mod routes;

use config::Config;
use contracts::advisor::AdvisorAgreementContract;
use contracts::passport::FinancialPassportContract;

// ──────────────────────────────────────────────
// Application State
// ──────────────────────────────────────────────

/// Shared application state accessible from all route handlers.
pub struct AppState {
    pub config: Config,
    pub passport_contract: FinancialPassportContract<SignerMiddleware<Provider<Http>, LocalWallet>>,
    pub advisor_contract: AdvisorAgreementContract<SignerMiddleware<Provider<Http>, LocalWallet>>,
    pub provider: Provider<Http>,
    pub db_pool: sqlx::PgPool,
}

// ──────────────────────────────────────────────
// Config injection middleware
// ──────────────────────────────────────────────

async fn inject_config(
    State(state): State<Arc<AppState>>,
    mut request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    request.extensions_mut().insert(state.config.clone());
    next.run(request).await
}

// ──────────────────────────────────────────────
// Health check
// ──────────────────────────────────────────────

async fn health_check(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    // Ping the RPC to verify connection
    let rpc_connected = state.provider.get_block_number().await.is_ok();

    (
        StatusCode::OK,
        Json(json!({
            "status": "ok",
            "rpc_connected": rpc_connected,
            "network": "Sepolia",
            "chain_id": state.config.chain_id,
            "contracts": {
                "passport": state.config.passport_contract_address,
                "advisor": state.config.advisor_contract_address,
            }
        })),
    )
}

// ──────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────

#[tokio::main]
async fn main() {
    // Load .env file
    dotenvy::dotenv().ok();

    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    // Load config
    let config = Config::from_env();
    tracing::info!("Starting GoalPath AI Blockchain Bridge API on port {}", config.port);
    tracing::info!("RPC URL: {}", config.rpc_url);
    tracing::info!("Passport contract: {}", config.passport_contract_address);
    tracing::info!("Advisor contract: {}", config.advisor_contract_address);

    // Set up Ethereum provider + signer
    let provider = Provider::<Http>::try_from(&config.rpc_url)
        .expect("Failed to create provider");

    let chain_id = config.chain_id;

    let wallet: LocalWallet = config
        .private_key
        .parse::<LocalWallet>()
        .expect("Failed to parse PRIVATE_KEY")
        .with_chain_id(chain_id);

    // Wrap with NonceManagerMiddleware for concurrent request safety
    let signer = SignerMiddleware::new(
        provider.clone(),
        wallet,
    );
    let signer = Arc::new(signer);

    // Create contract instances
    let passport_address: Address = config
        .passport_contract_address
        .parse()
        .expect("Invalid PASSPORT_CONTRACT_ADDRESS");

    let advisor_address: Address = config
        .advisor_contract_address
        .parse()
        .expect("Invalid ADVISOR_CONTRACT_ADDRESS");

    let passport_contract =
        FinancialPassportContract::new(passport_address, signer.clone());
    let advisor_contract =
        AdvisorAgreementContract::new(advisor_address, signer.clone());

    // Initialize database pool with PgBouncer compatibility
    let connect_options = sqlx::postgres::PgConnectOptions::from_str(&config.database_url)
        .expect("Invalid DATABASE_URL")
        .statement_cache_capacity(0); // Disable prepared statements to fix Supabase PgBouncer (Port 6543) error "42P05"

    let db_pool = sqlx::postgres::PgPoolOptions::new()
        .connect_with(connect_options)
        .await
        .expect("Failed to connect to PostgreSQL");

    // Initialize ca_profiles table if it doesn't exist
    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS ca_profiles (
            wallet VARCHAR(42) PRIMARY KEY,
            name VARCHAR(255),
            email VARCHAR(255),
            phone VARCHAR(50),
            years_experience INTEGER
        );
        "#,
    )
    .execute(&db_pool)
    .await
    .expect("Failed to create ca_profiles table");

    // Build shared state
    let state = Arc::new(AppState {
        config: config.clone(),
        passport_contract,
        advisor_contract,
        provider: provider.clone(),
        db_pool,
    });

    // CORS — allow the Python backend and any origin during dev
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    // Build router
    let app = Router::new()
        // Health check (no auth)
        .route("/chain/health", get(health_check))
        // Passport endpoints
        .route("/chain/passport/mint", post(routes::passport::mint_passport))
        .route("/chain/passport/update", post(routes::passport::update_passport))
        .route("/chain/passport/{wallet}", get(routes::passport::get_passport))
        // Event endpoints
        .route("/chain/events/log", post(routes::events::log_event))
        .route("/chain/events/{plan_id}", get(routes::events::get_events))
        // Advisor endpoints
        .route("/chain/advisors/register", post(routes::advisors::register_advisor))
        .route("/chain/advisors/verify", post(routes::advisors::verify_advisor))
        .route("/chain/advisors/list", get(routes::advisors::list_advisors))
        // Identity endpoint
        .route("/chain/identity/{user_wallet}", get(routes::identity::get_identity))
        // Middleware
        .layer(axum_middleware::from_fn(middleware::auth::auth_middleware))
        .layer(axum_middleware::from_fn_with_state(state.clone(), inject_config))
        .layer(cors)
        .with_state(state);

    // Start server
    let addr = format!("0.0.0.0:{}", config.port);
    tracing::info!("Listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("Failed to bind address");

    axum::serve(listener, app)
        .await
        .expect("Server error");
}
