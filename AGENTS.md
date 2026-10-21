# AGENTS.md

## Project Overview

**BeerStat consumer** is a Rust service that bridges RabbitMQ and the BeerStat API.
It listens on the `bs_donats` queue (virtual host `gunlinux_bot`) for raw
DonationAlerts donation payloads from an upstream bot, keeps paid donations, and
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
│   └── message.rs     # DonationPayload parsing, Donation body, rounding
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
| `BEER_DLQ` | `<BEER_STAT>.dlq` | Dead-letter routing key on the `dlq` exchange |
| `RUST_LOG` | `info` | Log filter |

## Architecture Notes

### Consumer flow

1. Upstream bot publishes DonationAlerts donation payloads to RabbitMQ queue
   `bs_donats` (durable, with DLQ).
2. `consume()` declares the queue with the dead-letter arguments and consumes
   with manual acknowledgement.
3. `handle()` parses `DonationPayload`, skips anything that is not a paid
   donation, builds a `Donation`, and POSTs it to `BEER_URL`.
4. `main()` acks on success and rejects without requeue on error (message goes to
   the DLQ), then reconnects after 5 seconds if the broker connection dies.

### Message contract

The queue carries the raw DonationAlerts payload (see `payload.json`):

```json
{
  "amount": 333,
  "amount_in_user_currency": 333,
  "created_at": "2026-10-11 18:29:48",
  "currency": "RUB",
  "id": 192333054,
  "message": "ahaha",
  "name": "Donations",
  "username": "loki"
}
```

Unknown keys (ids, recipient, provider metadata) are ignored. Only
`amount_in_user_currency` (int or float), `name` and `message` are used:
`amount_in_user_currency` is rounded half-to-even into `value`, an empty `name`
becomes `"Anonym"`, and a missing or blank `message` becomes `commentary: null`.
The POST body is `{ date, value, name, commentary }`; `date` is the processing
time in UTC. The queue is expected to carry donations only, so there is no
`event_type` filter.

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
- **DLQ is broker-side.** Failures are rejected without requeue, so
  `x-dead-letter-exchange=dlq` plus `x-dead-letter-routing-key=<BEER_DLQ>`
  routes them to `<queue>.dlq`. Neither the exchange nor that queue is declared
  here; declare them on the producer side or the broker drops the message. An
  existing queue with different arguments fails the re-declare
  (`PRECONDITION_FAILED`).
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
