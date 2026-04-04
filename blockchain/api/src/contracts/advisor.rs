use ethers::prelude::abigen;

// Generate type-safe Rust bindings from the AdvisorAgreement ABI
abigen!(
    AdvisorAgreementContract,
    "abi/AdvisorAgreement.json",
    event_derives(serde::Deserialize, serde::Serialize)
);
