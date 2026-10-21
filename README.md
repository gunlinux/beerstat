# BeerStat consumer

RabbitMQ consumer for beer donations. Locally it defaults to the `bs_donats`
queue in virtual host `gunlinux_bot`; production consumes the `donations` queue
of the `donation_alerts` broker (vhost `prod`). It keeps paid donations and
forwards them to the BeerStat API:

```json
{ "date": "2026-10-11T18:29:48.123456+00:00", "value": 333, "name": "loki", "commentary": "ahaha" }
```

The queue carries the raw DonationAlerts donation payload (see `payload.json`);
unknown fields are ignored. `amount_in_user_currency` becomes `value`, an empty
`name` becomes `Anonym`, and a missing or blank `message` becomes
`commentary: null`.

The API and its database live in another project: this repository holds only the
consumer, so it needs a reachable `/donate` endpoint to be useful.

## Requirements

- Rust 1.85+ (edition 2024; `rust-version` is set in `Cargo.toml`)
- A running RabbitMQ broker; production reuses the `donation_alerts` broker
  (`127.0.0.1:5674`, virtual host `prod`) and consumes its `donations` queue
- A running BeerStat API (default `http://127.0.0.1:6016/donate`)

## Configuration

Read from the environment, or from a `.env` file in the working directory
(see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `RABBIT_URL` | `amqp://user:password@localhost:5672/gunlinux_bot` | Broker URI, virtual host in the path |
| `BEER_URL` | `http://127.0.0.1:6016/donate` | Donate endpoint to POST to |
| `BEER_STAT` | `bs_donats` | Queue name |
| `BEER_DLQ` | `<BEER_STAT>.dlq` | Dead-letter routing key; empty/`-`/`off`/`none` disables dead-letter arguments |
| `RUST_LOG` | `info` | Log filter (`debug` logs each parsed event) |

The virtual host is part of the URI path, so
`amqp://user:pass@host:5672/gunlinux_bot` joins vhost `gunlinux_bot`. A URL
without a path means the default vhost `/`; a leftover `RABBIT_VHOST` variable is
ignored and logged as a warning.

## Running

```bash
make dev      # cargo build
make run      # cargo run
make release  # optimized binary in target/release/beerstat
```

## Deployment

CI is the deployment: `.github/workflows/code-quality.yaml` runs on every push;
when it passes on `master`, `.github/workflows/deploy.yaml` builds the Docker
image, ships it to gunlinux.ru over SSH (`docker save | docker load`) and runs
`.github/deploy.sh` there. The only secret is `PRIVATE_KEY_SSH`, an SSH key
authorized for `loki@gunlinux.ru`; there is no registry and no Docker Hub
credentials.

On the server:

| Item | Value |
|---|---|
| checkout | `/home/loki/projects/bot/beerstat` (`git reset --hard origin/master`) |
| runtime config | `.env` in that checkout, gitignored, survives deploys |
| image | `beerstat:<short-sha>` |
| unit / container | `beerstat.service` / `beerstat` |
| logs | `sudo journalctl -u beerstat -f` |

The first deploy disables the legacy Python `bot@beer_consumer.service`. The
container uses host networking because the broker and the API listen on
`127.0.0.1`. It runs as the deploying user (`--user $(id -u):$(id -g)`) so the
mounted `.env` stays readable.

A production `.env` reuses the `donation_alerts` broker and queue:

```dotenv
RABBIT_URL=amqp://donate_consumer:password@127.0.0.1:5674/prod
BEER_URL=http://127.0.0.1:6016/donate
BEER_STAT=donations
BEER_DLQ=-
RUST_LOG=info
```

`BEER_DLQ=-` is required here: `donation_alerts` declares `donations` without
`x-dead-letter-*` arguments, and a mismatching re-declare fails with
`PRECONDITION_FAILED`.

### Local Docker

```bash
make docker                      # docker build -t beerstat:latest .
docker run -d --name beerstat \
  --restart unless-stopped \
  --env-file .env \
  beerstat:latest
```

The image is a two-stage build: a static musl binary (rustls, no OpenSSL) is
compiled on `rust:1.96-alpine` and the runtime is `scratch` plus a CA bundle and
that binary. There is no shell, libc or package manager. Config comes from
`--env-file`/`-e`; a `.env` file inside the image is neither copied nor needed.
`SIGTERM` (docker stop, systemd) shuts the consumer down like Ctrl-C.

## Behaviour

- The queue is declared durable, not auto-deleted. By default it also carries
  `x-dead-letter-exchange=dlq` and `x-dead-letter-routing-key=<BEER_DLQ>`; the
  exchange and target queue are not declared here, so they must exist on the
  producer side or the broker drops the dead-lettered message. With
  `BEER_DLQ=-` no dead-letter arguments are declared at all, which is what a
  queue shared with another producer requires.
- A failed POST (network error or HTTP error status) rejects the message
  without requeue: it is dead-lettered when a DLQ is configured, otherwise the
  broker drops it.
- Donations with a zero, negative or missing `amount_in_user_currency` are
  acked and ignored. A payload that fails to parse is rejected without requeue.
- Amounts are rounded half-to-even, matching the previous Python consumer.
- An empty `name` is sent as `Anonym`; an empty `message` is sent as
  `commentary: null`.
- On broker errors the consumer logs, then reconnects after 5 seconds. Ctrl-C
  exits; a message that was in flight is left unacked and redelivered by the
  broker.

## Checks

```bash
make check    # fmt + clippy + tests
```
