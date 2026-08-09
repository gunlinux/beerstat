# AGENTS.md

## Project Overview

**BeerStat** is a Flask-based web application for tracking beer donations. It has two components:

1. **Flask REST API** (`run.py`, `app/`) — `POST /donate` records a donation, `GET /balance` returns the cumulative total.
2. **RabbitMQ consumer** (`beer_consumer.py`) — listens on the `bs_donats` queue (virtual host `gunlinux_bot`) for donation events from an upstream bot, transforms them via `BeerConsumer._from_queue_event_to_bs`, and POSTs them to the Flask API.

The app is deployed on an Ubuntu VPS via systemd units (`services/`).

## Tech Stack

- **Python** 3.12+
- **Package manager:** [uv](https://docs.astral.sh/uv/)
- **Web framework:** Flask + Flask-SQLAlchemy + Flask-Migrate + Flask-Admin
- **Database:** SQLite (in-memory for tests, file `instance/mydatabase.db` for dev, configurable via `SQLALCHEMY_DATABASE_URI`)
- **Message queue:** RabbitMQ, consumed via [FastStream](https://faststream.airt.ai/) with manual ack
- **Async HTTP:** aiohttp (consumer → API)
- **Data validation:** Pydantic (queue message models)
- **Production WSGI:** Gunicorn (3 workers, bound to `127.0.0.1:6016`)
- **Testing:** pytest + pytest-asyncio
- **Linting/formatting:** ruff
- **Type checking:** pyright

## Project Structure

```
beerstat/
├── app/
│   ├── __init__.py      # Flask app factory, routes (/donate, /balance), admin setup
│   ├── extensions.py    # SQLAlchemy instance
│   ├── models.py        # BeerDonation model
│   ├── settings.py      # env-var config (RABBIT_URL, BEER_URL, etc.)
│   └── utils.py         # insert_donate(), get_sum()
├── tests/
│   ├── test_basics.py        # Flask endpoint unit tests
│   ├── test_integration.py   # End-to-end donate-then-balance test
│   └── test_beer_consumer.py # Consumer unit tests
├── migrations/           # Alembic migrations (via Flask-Migrate)
├── services/             # systemd unit files for deployment
├── beer_consumer.py      # RabbitMQ consumer entry point
├── run.py                # Flask dev server entry point
├── pyproject.toml        # Project config + tool settings
└── Makefile              # dev/test/lint/format/type-check targets
```

## Building and Running

```bash
# Install dependencies
make dev

# Create database + run migrations
mkdir -p instance
uv run flask db upgrade

# Run Flask dev server
uv run python run.py

# Run RabbitMQ consumer
uv run python beer_consumer.py

# Run tests
make test           # quiet
make test-dev       # verbose with stdout

# Run linting
make lint

# Run type checking
make types

# Auto-format + auto-fix lint issues
make fix

# Full CI check (tests + lint + format + types)
make check
```

## Environment Variables

Set via `.env` or the environment. See `app/settings.py`:

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://127.0.0.1/2` | Redis connection (currently unused in code) |
| `RABBIT_URL` | `amqp://user:password@localhost:5672/` | RabbitMQ broker URL |
| `BEER_URL` | `http://127.0.0.1:6016/donate` | Donate endpoint the consumer POSTs to |
| `SECRET_KEY` | `TypeMeIn` | Flask secret key (set in production) |
| `SQLALCHEMY_DATABASE_URI` | `sqlite:///mydatabase.db` | Database connection string |

The consumer queue name is hardcoded as `bs_donats` in `app/settings.py` (`BEER_STAT`).

## Architecture Notes

### Consumer → API flow

1. Upstream bot publishes donation events to RabbitMQ queue `bs_donats` (durable, with DLQ).
2. `beer_consumer.py` subscribes via FastStream with `MANUAL` ack policy.
3. `BeerConsumer.on_message()` filters for `event_type == "DONATION"` with non-zero amount, transforms via `_from_queue_event_to_bs` (rounds amount to int), and POSTs to the Flask `/donate` endpoint.
4. `process_message()` wraps the handler: acks on success, rejects on exception (message goes to DLQ).

### Flask app

- Factory pattern: `create_app(testing=False)` in `app/__init__.py`.
- `insert_donate()` creates a `BeerDonation` row and commits.
- `get_sum()` returns `SUM(value)` or `None` if no donations exist.
- Flask-Admin exposes the `BeerDonation` model at `/admin`.

## Development Conventions

- **Testing:** Tests live in `tests/`. In-memory SQLite is used (`create_app(testing=True)`). Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`.
- **Type hints:** Used throughout. pyright is configured with relaxed rules (see `[tool.pyright]` in `pyproject.toml`).
- **Linting:** ruff with default rules. Format with `ruff format`, fix with `ruff check --fix`.
- **Migrations:** Managed via Flask-Migrate/Alembic. After model changes, run `uv run flask db migrate -m "description"` then `uv run flask db upgrade`.
- **Imports:** Type-checker pragmas (`# pyright: ignore[...]`) are used sparingly where SQLAlchemy dynamic attributes conflict with static analysis.

## CI/CD

GitHub Actions (`.github/workflows/code-quality.yaml`) runs on every push:
- `uv lock --locked` — verifies lock file is up to date
- `ruff check` — linting
- `ruff format --check` — formatting check
- `pyright` — type checking

Tests are **not** run in CI currently.
