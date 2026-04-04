use std::env;

/// Application configuration loaded from environment variables.
#[derive(Debug, Clone)]
pub struct Config {
    pub rpc_url: String,
    pub private_key: String,
    pub passport_contract_address: String,
    pub advisor_contract_address: String,
    pub goalpath_internal_key: String,
    pub admin_key: String,
    pub port: u16,
    pub etherscan_base_url: String,
    pub chain_id: u64,
}

impl Config {
    /// Load configuration from environment variables.
    /// Panics with a descriptive message if any required variable is missing.
    pub fn from_env() -> Self {
        Self {
            rpc_url: env::var("RPC_URL")
                .expect("RPC_URL must be set"),
            private_key: env::var("PRIVATE_KEY")
                .expect("PRIVATE_KEY must be set"),
            passport_contract_address: env::var("PASSPORT_CONTRACT_ADDRESS")
                .expect("PASSPORT_CONTRACT_ADDRESS must be set"),
            advisor_contract_address: env::var("ADVISOR_CONTRACT_ADDRESS")
                .expect("ADVISOR_CONTRACT_ADDRESS must be set"),
            goalpath_internal_key: env::var("GOALPATH_INTERNAL_KEY")
                .expect("GOALPATH_INTERNAL_KEY must be set"),
            admin_key: env::var("ADMIN_KEY")
                .expect("ADMIN_KEY must be set"),
            port: env::var("PORT")
                .unwrap_or_else(|_| "3001".to_string())
                .parse()
                .expect("PORT must be a valid u16"),
            etherscan_base_url: env::var("ETHERSCAN_BASE_URL")
                .unwrap_or_else(|_| "https://sepolia.etherscan.io".to_string()),
            chain_id: env::var("CHAIN_ID")
                .unwrap_or_else(|_| "11155111".to_string())
                .parse()
                .expect("CHAIN_ID must be a valid u64"),
        }
    }
}
