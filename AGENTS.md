# AGENTS.md

## Project Overview

**BeerStat consumer** is a Rust service that bridges RabbitMQ and the BeerStat API.
It listens on the `bs_donats` queue (virtual host `gunlinux_bot`) for donation
events from an upstream bot, keeps `DONATION` events with a non-zero amount, and
POSTs them to the donate endpoint. The API and its database live in another
project; this repository holds only the consumer.

## Tech Stack

- **Rust** 2024 edition (min 1.85), binary crate `beerstat`
- **AMQP:** [lapin](https://docs.rs/lapin) 3 over tokio
- **Async HTTP:** reqwest (10 s timeout)
- **Data validation:** serde / serde_json
- **Logging:** tracing + tracing-subscriber (`RUST_LOG`)
- **Config:** environment variables, optional `.env` via dotenvy
- **TLS:** rustls on both sides (lapin and reqwest); no OpenSSL anywhere
- **Deployment:** Docker image (`Dockerfile`) or systemd unit in `services/`

## Project Structure

```
beerstat/
├── src/
│   ├── main.rs        # broker connection, consume loop, ack/reject, HTTP post
│   ├── config.rs      # env config
│   └── message.rs     # QueueMessage/QueueEvent models, Donation payload, rounding
├── services/
│   └── bot@beer_consumer.service   # runs target/release/beerstat
├── .github/workflows/
│   └── code-quality.yaml           # fmt, clippy, tests
├── .env.example       # documented defaults; copy to .env
├── Dockerfile         # two-stage: rust:1.96-alpine (musl, static) -> scratch
├── .dockerignore
├── Cargo.toml
├── Cargo.lock         # committed, this is a binary
└── Makefile
```

There is no Python code, database, migrations or HTTP API in this repository
anymore. `beer.db` / `instance/` may still be lying around locally from the old
deployment; they are gitignored and must not be depended on.

## Building and Running

```bash
make dev      # cargo build
make run      # cargo run
make test     # cargo test
make check    # fmt + clippy + tests (same as CI)
make fix      # fmt + clippy --fix
make release  # cargo build --release
make docker   # docker build -t beerstat:latest .
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `RABBIT_URL` | `amqp://user:password@localhost:5672/gunlinux_bot` | Broker URI, virtual host in the path |
| `BEER_URL` | `http://127.0.0.1:6016/donate` | Donate endpoint the consumer POSTs to |
| `BEER_STAT` | `bs_donats` | Queue name |
| `RUST_LOG` | `info` | Log filter |

## Architecture Notes

### Consumer flow

1. Upstream bot publishes donation events to RabbitMQ queue `bs_donats` (durable, with DLQ).
2. `consume()` declares the queue with the dead-letter arguments and consumes
   with manual acknowledgement.
3. `handle()` parses `QueueMessage`, skips anything that is not a paid donation,
   builds a `Donation`, and POSTs it to `BEER_URL`.
4. `main()` acks on success and rejects without requeue on error (message goes to
   the DLQ), then reconnects after 5 seconds if the broker connection dies.

### Message contract

```json
{
  "event": "donation",
  "source": "donationalerts",
  "data": { "event_type": "DONATION", "user_name": "Cher_cash", "amount": 100.5 }
}
```

`event` and `data.event_type` are required; `source` defaults to `""`; the other
event fields are optional. Unknown keys are ignored on purpose (producers add
provider metadata and raw payloads). `data.amount` is rounded half-to-even to an
integer, and the POST body is `{ date, value, name }` with `name: null` when the
producer sent no user name.

## Gotchas

- **Virtual host lives in `RABBIT_URL`.** lapin has no separate `virtualhost`
  option, so there is deliberately no `RABBIT_VHOST`: use
  `amqp://host:5672/gunlinux_bot`. A URI without a path silently means vhost
  `/`; a stale `RABBIT_VHOST` now only triggers a startup warning.
- **lapin 3 API differs from older examples.** Acks go through
  `delivery.acker.ack(..)` / `.reject(..)`; `queue_declare` and `basic_consume`
  take `&str`, not `Queue`; queue arguments need
  `AMQPValue::LongString(..)`.
- **The `dlq` exchange is not declared here** — it belongs to the producing side.
  If it is missing, rejected messages are dropped by the broker.
- **Reject means dead-letter, not retry.** Transient API outages therefore lose
  the event to the DLQ; that matches the previous Python consumer.
- **Rounding is half-to-even**, not `f64::round`, so amounts stay identical to
  the historical data (`100.5 -> 100`).
- **No OpenSSL.** Both reqwest (`rustls-tls`) and lapin (`rustls` default) avoid
  it, which is why the runtime image only needs `ca-certificates`. Keep it that
  way when adding dependencies.
- **`SIGTERM` and Ctrl-C are both handled** via `shutdown_signal()`; `docker
  stop` and `systemctl stop` do not have to wait for a timeout.

## Development Conventions

- Tests are unit tests next to the code (`#[cfg(test)]`), ported from the old
  Python consumer suite: filtering, transform, message parsing.
  There is no live-broker integration test.
- Keep changes consistent with rustfmt defaults and `clippy -D warnings`
  (CI enforces both).
- `Cargo.lock` is committed; do not regenerate it casually.
- Schema/behaviour changes must stay compatible with the deployed API and the
  upstream producer.

## Deployment

- **Docker:** `make docker`, then run with `--env-file .env` (or `-e` flags);
  config is never baked into the image. The container runs as uid 10001.
- **systemd:** `make release` and `services/bot@beer_consumer.service`, which
  loads `.env` from the checkout directory.
- Required runtime config is only `RABBIT_URL` and `BEER_URL`; everything else
  has a default (see table above). It needs network access to the broker and
  the API.
- TLS trust comes from the system CA bundle: the Docker image installs
  `ca-certificates`, while the systemd unit keeps the host's `SSL_CERT_FILE` /
  `SSL_CERT_DIR` settings for the same purpose.

## CI/CD

GitHub Actions (`.github/workflows/code-quality.yaml`) runs on every push:
`cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`.
Tests do run in CI for this project, unlike the old Python workflow.
