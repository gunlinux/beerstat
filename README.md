# BeerStat consumer

RabbitMQ consumer for beer donations. It subscribes to the `bs_donats` queue
(virtual host `gunlinux_bot`), keeps paid donations and forwards them to the
BeerStat API:

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
- A running RabbitMQ broker with the `gunlinux_bot` virtual host and the `dlq`
  exchange used for dead-lettering
- A running BeerStat API (default `http://127.0.0.1:6016/donate`)

## Configuration

Read from the environment, or from a `.env` file in the working directory
(see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `RABBIT_URL` | `amqp://user:password@localhost:5672/gunlinux_bot` | Broker URI, virtual host in the path |
| `BEER_URL` | `http://127.0.0.1:6016/donate` | Donate endpoint to POST to |
| `BEER_STAT` | `bs_donats` | Queue name |
| `BEER_DLQ` | `<BEER_STAT>.dlq` | Dead-letter routing key on the `dlq` exchange |
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

### Docker

```bash
make docker                      # docker build -t beerstat:latest .
docker run -d --name beerstat \
  --restart unless-stopped \
  --env-file .env \
  beerstat:latest
```

The image is a two-stage build: a static musl binary (rustls, no OpenSSL) is
compiled on `rust:1.96-alpine` and the runtime is `scratch` plus a CA bundle and
that binary. There is no shell, libc or package manager, and it runs as uid/gid
10001. Config comes from `--env-file`/`-e`; a `.env` file inside the image is
neither copied nor needed.

Every variable above has a default, so the only ones a real deployment must set
are `RABBIT_URL` and `BEER_URL`:

```bash
docker run -d --name beerstat --restart unless-stopped \
  -e RABBIT_URL='amqp://user:pass@rabbit:5672/gunlinux_bot' \
  -e BEER_URL='http://bs:6016/donate' \
  -e RUST_LOG=info \
  beerstat:latest
```

`SIGTERM` (docker stop, systemd) shuts the consumer down like Ctrl-C.

### systemd

```bash
make release
sudo cp services/bot@beer_consumer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now 'bot@beer_consumer.service'
```

The unit runs `target/release/beerstat` from `/home/loki/projects/bot/beerstat/`
and loads `.env` from there. Adjust paths if the checkout lives elsewhere.

## Behaviour

- The queue is declared durable, not auto-deleted, with
  `x-dead-letter-exchange=dlq` and `x-dead-letter-routing-key=<BEER_DLQ>`.
  The exchange and the target queue (`bs_donats.dlq` by default) are not
  declared here: they must already exist on the producer side, otherwise the
  broker drops the dead-lettered message. A queue that already exists with
  different arguments makes the declare fail (`PRECONDITION_FAILED`), so
  recreate it or keep `BEER_DLQ` matching its routing key.
- A failed POST (network error or HTTP error status) rejects the message
  without requeue, so the broker dead-letters it to `bs_donats.dlq`.
- Donations with a zero, negative or missing `amount_in_user_currency` are
  acked and ignored. A payload that fails to parse is rejected to the DLQ.
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
