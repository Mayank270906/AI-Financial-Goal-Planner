FROM rust:1.76-slim AS builder
WORKDIR /app

# Install standard dependencies for compiling OpenSSL if needed
RUN apt-get update \
    && apt-get install -y pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire API directory
COPY . .

# Build the release binary
RUN cargo build --release

# ----------------- #
# Runtime container #
# ----------------- #
FROM debian:bookworm-slim

# Install ca-certificates needed for HTTPS requests (and DB connection)
RUN apt-get update \
    && apt-get install -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the compiled binary from the builder stage
COPY --from=builder /app/target/release/goalpath-chain-api /usr/local/bin/

# Expose the default port Render looks for
EXPOSE 3001

# Run the binary
CMD ["goalpath-chain-api"]
