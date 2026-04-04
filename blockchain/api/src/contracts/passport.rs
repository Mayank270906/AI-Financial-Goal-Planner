use ethers::prelude::abigen;

// Generate type-safe Rust bindings from the FinancialPassport ABI
abigen!(
    FinancialPassportContract,
    "abi/FinancialPassport.json",
    event_derives(serde::Deserialize, serde::Serialize)
);
