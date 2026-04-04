# GoalPath AI — Blockchain Backend

India's first mathematically rigorous, AI-explained, **on-chain** financial planning system.

This directory contains the blockchain layer that sits alongside the existing Python/FastAPI backend. It provides cryptographic proof-of-plan via soulbound NFTs and an immutable advisor engagement ledger.

---

## Architecture

```
┌─────────────────────────┐
│  GoalPath AI Python     │
│  Backend (FastAPI)      │
│  ai-financial-goal-     │
│  planner.onrender.com   │
└──────────┬──────────────┘
           │ HTTP + Bearer Token
           ▼
┌─────────────────────────┐
│  Rust Axum Bridge API   │
│  localhost:3001          │
│  /chain/*               │
└──────────┬──────────────┘
           │ ethers-rs (JSON-RPC)
           ▼
┌─────────────────────────┐
│  Solidity Smart         │
│  Contracts on Sepolia   │
│                         │
│  • FinancialPassport    │
│    (Soulbound NFT)      │
│  • AdvisorAgreement     │
│    (6-Event Ledger)     │
└─────────────────────────┘
```

---

## Smart Contracts

### 1. FinancialPassport (Soulbound NFT)

A non-transferable ERC721 token implementing [EIP-5192](https://eips.ethereum.org/EIPS/eip-5192) that stores the SHA-256 hash of a user's GoalPath AI financial plan on-chain.

- **Mint**: Create a new passport for a user wallet
- **Update**: Update the plan hash when the financial plan changes
- **Verify**: Cryptographically verify a plan hash against on-chain data
- **Soulbound**: Cannot be transferred — it's an identity document

### 2. AdvisorAgreement (CA Portal)

Records the immutable 6-event engagement lifecycle between a user and a financial advisor (CA). All sensitive user data is stored as SHA-256 hashes — never in plaintext.

**The 6 on-chain events:**
| # | Event | What's recorded on-chain |
|---|-------|--------------------------|
| 0 | `AGREEMENT_CREATED` | User-CA agreement terms (fee, duration, scope) |
| 1 | `PLAN_SHARED` | Hash of user's plan shared with CA |
| 2 | `ADVISOR_RECOMMENDATION` | Hash of CA's recommendation |
| 3 | `USER_APPROVAL` | User's cryptographic consent/rejection |
| 4 | `PLAN_UPDATED_AFTER_ADVICE` | Old plan hash → new plan hash delta |
| 5 | `ENGAGEMENT_CLOSED` | Outcome (completed/disputed/abandoned) + fee |

---

## Prerequisites

- [Foundry](https://book.getfoundry.sh/getting-started/installation) (forge, cast, anvil)
- [Rust](https://rustup.rs/) ≥ 1.75
- A Sepolia testnet wallet with ETH for gas (get free ETH from [sepoliafaucet.com](https://sepoliafaucet.com))

---

## Quick Start

### 1. Run Foundry Tests

```bash
cd blockchain/contracts
forge test -vv
```

Expected output: **13 tests passed** (8 for FinancialPassport, 5 for AdvisorAgreement).

### 2. Deploy Contracts to Sepolia

```bash
cd blockchain/contracts

# Set environment variables
export PRIVATE_KEY=0xYOUR_PRIVATE_KEY
export RPC_URL=https://rpc.sepolia.org
export ETHERSCAN_API_KEY=YOUR_KEY  # optional, for verification

# Deploy FinancialPassport
forge script script/DeployFinancialPassport.s.sol \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --broadcast \
  --verify \
  --etherscan-api-key $ETHERSCAN_API_KEY

# Deploy AdvisorAgreement
forge script script/DeployAdvisorAgreement.s.sol \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --broadcast \
  --verify \
  --etherscan-api-key $ETHERSCAN_API_KEY
```

### 3. Start the Rust API

```bash
cd blockchain/api

# Copy and fill in env vars
cp .env.example .env
# Edit .env with your deployed contract addresses and private key

# Run the server
cargo run
```

The API starts at `http://localhost:3001`.

### 4. Verify it's running

```bash
curl http://localhost:3001/chain/health
```

---

## API Endpoints

All endpoints (except `/chain/health`) require:
```
Authorization: Bearer GOALPATH_INTERNAL_KEY_2026
```

### Integration Endpoints (called by Python backend)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chain/passport/mint` | Mint a soulbound financial passport |
| `POST` | `/chain/passport/update` | Update the plan hash |
| `POST` | `/chain/events/log` | Log a CA engagement event |

### Verification Endpoints (for third-party fintechs)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/chain/passport/:wallet` | Get passport data for a wallet |
| `GET` | `/chain/events/:plan_id` | Get all events for a plan |
| `GET` | `/chain/advisors/list` | List all registered advisors |
| `GET` | `/chain/identity/:wallet` | Full identity card (passport + token ID) |

### Admin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chain/advisors/register` | Register a new CA |
| `POST` | `/chain/advisors/verify` | Admin-verify a CA (requires ADMIN_KEY) |

---

## Request/Response Examples

### Mint Passport

```bash
curl -X POST http://localhost:3001/chain/passport/mint \
  -H "Authorization: Bearer GOALPATH_INTERNAL_KEY_2026" \
  -H "Content-Type: application/json" \
  -d '{
    "user_wallet": "0xABC...",
    "plan_hash": "a3f9c2d1..."
  }'
```

Response:
```json
{
  "success": true,
  "tx_hash": "0x...",
  "block_number": 45678912,
  "token_id": 42,
  "etherscan": "https://sepolia.etherscan.io/tx/0x..."
}
```

### Log Engagement Event

```bash
curl -X POST http://localhost:3001/chain/events/log \
  -H "Authorization: Bearer GOALPATH_INTERNAL_KEY_2026" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": 0,
    "plan_id": "plan_abc123",
    "primary_hash": "a3f9c2d1...",
    "user_wallet": "0xABC...",
    "advisor_wallet": "0xDEF...",
    "fee_amount": "1000000000000000000",
    "duration_days": 30,
    "service_scope": "Full financial planning"
  }'
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RPC_URL` | ✅ | Sepolia RPC endpoint |
| `PRIVATE_KEY` | ✅ | GoalPath AI operator wallet private key (0x-prefixed) |
| `PASSPORT_CONTRACT_ADDRESS` | ✅ | Deployed FinancialPassport contract address |
| `ADVISOR_CONTRACT_ADDRESS` | ✅ | Deployed AdvisorAgreement contract address |
| `GOALPATH_INTERNAL_KEY` | ✅ | Shared API key for Python backend auth |
| `ADMIN_KEY` | ✅ | Separate admin key for advisor verification |
| `PORT` | ❌ | Server port (default: 3001) |
| `ETHERSCAN_BASE_URL` | ❌ | Block explorer URL (default: https://sepolia.etherscan.io) |
| `CHAIN_ID` | ❌ | Chain ID (default: 11155111 for Sepolia) |

---

## Deployment Options

The Rust API compiles to a single static binary. Hosting options:

- **[Railway](https://railway.app)** — `cargo build --release`, deploy binary
- **[Render](https://render.com)** — Docker or native Rust buildpack
- **[Fly.io](https://fly.io)** — `fly launch` with Dockerfile

### Dockerfile

```dockerfile
FROM rust:1.76-slim AS builder
WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/goalpath-chain-api /usr/local/bin/
CMD ["goalpath-chain-api"]
```

---

## Project Structure

```
blockchain/
├── contracts/                   # Foundry project
│   ├── foundry.toml
│   ├── src/
│   │   ├── IERC5192.sol                   # EIP-5192 interface
│   │   ├── FinancialPassport.sol          # Soulbound NFT
│   │   └── AdvisorAgreement.sol           # CA engagement ledger
│   ├── test/
│   │   ├── FinancialPassport.t.sol        # 8 tests
│   │   └── AdvisorAgreement.t.sol         # 5 tests
│   └── script/
│       ├── DeployFinancialPassport.s.sol
│       └── DeployAdvisorAgreement.s.sol
└── api/                         # Rust Axum bridge API
    ├── Cargo.toml
    ├── .env.example
    ├── abi/                     # Contract ABIs (auto-generated)
    └── src/
        ├── main.rs
        ├── config.rs
        ├── routes/
        │   ├── passport.rs      # /chain/passport/*
        │   ├── events.rs        # /chain/events/*
        │   ├── advisors.rs      # /chain/advisors/*
        │   └── identity.rs      # /chain/identity/*
        ├── contracts/
        │   ├── passport.rs      # ethers-rs bindings
        │   └── advisor.rs       # ethers-rs bindings
        └── middleware/
            └── auth.rs          # API key verification
```

---

## Privacy Model

All user financial data stays **off-chain** in the Python backend. Only **SHA-256 hashes** are stored on-chain:

- The plan itself → stored as `planHash` (32 bytes)
- CA recommendations → stored as `recommendationHash`
- User consent → stored as `approvalHash`

This means: **anyone can verify the integrity** of a financial plan (by comparing hashes), but **nobody can reverse-engineer** the actual plan data from the hash.

---

## License

MIT
