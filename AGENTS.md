# AGENTS.md

## Project Overview

**BeerStat consumer** is a Rust service that bridges RabbitMQ and the BeerStat API.
Locally the defaults are the `bs_donats` queue in virtual host `gunlinux_bot`;
production consumes the `donations` queue of the `donation_alerts` broker
(`127.0.0.1:5674`, vhost `prod`). It keeps paid donations and POSTs them to the
donate endpoint. The API and its database live in another project; this
repository holds only the consumer.

## Tech Stack

- **Rust** 2024 edition (min 1.85), binary crate `beerstat`
- **AMQP:** [lapin](https://docs.rs/lapin) 3 over tokio
- **Async HTTP:** reqwest (10 s timeout)
- **Data validation:** serde / serde_json
- **Logging:** tracing + tracing-subscriber (`RUST_LOG`)
- **Config:** environment variables, optional `.env` via dotenvy
- **TLS:** rustls on both sides (lapin and reqwest); no OpenSSL anywhere
- **Deployment:** Docker image (`Dockerfile`) shipped by GitHub Actions over SSH
  and run by the `deploy/beerstat.service` systemd unit

## Project Structure

```
beerstat/
├── src/
│   ├── main.rs        # broker connection, consume loop, ack/reject, HTTP post
│   ├── config.rs      # env config
│   └── message.rs     # DonationPayload parsing, Donation body, rounding
├── deploy/
│   └── beerstat.service            # runs the deployed image on the server
├── .github/
│   ├── deploy.sh                   # server-side deploy script (over SSH)
│   └── workflows/
│       ├── code-quality.yaml       # fmt, clippy, tests
│       └── deploy.yaml             # build image, ship, deploy on master
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
| `BEER_DLQ` | `<BEER_STAT>.dlq` | Dead-letter routing key; empty/`-`/`off`/`none` disables dead-letter arguments |
| `RUST_LOG` | `info` | Log filter |

## Architecture Notes

### Consumer flow

1. `donation_alerts` publishes raw DonationAlerts payloads to the `donations`
   queue on the `prod` vhost (durable, declared without DLQ arguments).
2. `consume()` declares the same queue (durable; dead-letter arguments only when
   `BEER_DLQ` is set) and consumes with manual acknowledgement.
3. `handle()` parses `DonationPayload`, skips anything that is not a paid
   donation, builds a `Donation`, and POSTs it to `BEER_URL`.
4. `main()` acks on success and rejects without requeue on error (dead-lettered
   when a DLQ is configured), then reconnects after 5 seconds if the broker
   connection dies.

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
- **DLQ is broker-side and optional.** `x-dead-letter-exchange=dlq` plus
  `x-dead-letter-routing-key=<BEER_DLQ>` routes failures to `<queue>.dlq`;
  neither the exchange nor that queue is declared here. An existing queue with
  different arguments fails the re-declare (`PRECONDITION_FAILED`), so the
  production `donations` queue (declared by `donation_alerts` without those
  arguments) requires `BEER_DLQ=-`.
- **Same queue, same arguments as `donation_alerts`.** It re-declares `donations`
  on every reconnect, so changing the queue arguments in beerstat would break
  the producer, not just the consumer.
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

- **Server:** gunlinux.ru, checkout `/home/loki/projects/bot/beerstat`, unit
  `beerstat.service`, container `beerstat`. The container uses host networking
  to reach the broker at `127.0.0.1:5674` and the API at `127.0.0.1:6016`.
- **Image:** built in CI (`Dockerfile`: static musl binary on
  `rust:1.96-alpine`, runtime `scratch` + CA bundle), shipped with
  `docker save | docker load`, tagged with the commit short SHA. No registry.
- **Config:** `.env` in the checkout, mounted at `/data`; it is gitignored and
  survives `git reset --hard`. Required: `RABBIT_URL`, `BEER_URL`; production
  also sets `BEER_STAT=donations` and `BEER_DLQ=-` to match the
  `donation_alerts` queue declaration.
- The deploy script disables the legacy `bot@beer_consumer.service` (the old
  Python consumer) on its first run.
- TLS trust comes from the CA bundle baked into the image.
- **Docker Hub is not used.** A local `make docker` still works for manual runs.

## CI/CD

GitHub Actions (`.github/workflows/code-quality.yaml`, workflow name
`Rust code quality`) runs on every push: `cargo fmt --check`,
`cargo clippy --all-targets -- -D warnings`, `cargo test`. When it passes on
`master`, `deploy.yaml` builds the image, ships it to the server over SSH and
runs `.github/deploy.sh` there. The only repository secret is
`PRIVATE_KEY_SSH` (authorized for `loki@gunlinux.ru`, port 187).
