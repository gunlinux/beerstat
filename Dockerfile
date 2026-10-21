# syntax=docker/dockerfile:1

# ---- stage 1: build a static musl binary ----
FROM rust:1.96-alpine AS builder

# aws-lc-rs (the rustls crypto provider) is compiled from C sources and needs
# cmake; alpine already has a musl toolchain, so the result is fully static.
RUN apk add --no-cache build-base cmake perl ca-certificates

WORKDIR /build

# Build dependencies first so source edits do not recompile the whole tree.
COPY Cargo.toml Cargo.lock ./
RUN mkdir src \
    && echo 'fn main() {}' > src/main.rs \
    && cargo build --release \
    && rm -rf src target/release/deps/beerstat*

COPY src ./src
RUN cargo build --release \
    && cp target/release/beerstat /build/beerstat

# ---- stage 2: runtime, just the binary and the CA bundle ----
FROM scratch

# rustls needs a trust store for amqps/https; the bundle is the only OS file
# the binary reads, so there is no libc, shell or package manager here.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    RUST_LOG=info
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /build/beerstat /beerstat

USER 10001:10001
ENTRYPOINT ["/beerstat"]
