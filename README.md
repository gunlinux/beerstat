# BeerStat - Beer Donation Tracker

BeerStat is a Flask-based web application designed to track beer donations. The application provides RESTful endpoints for recording donations and retrieving balance information.

## Prerequisites

- Python 3.12+
- UV package manager

## Setup

### 1. Install dependencies

```bash
make dev
```

### 2. Create the database

```bash
mkdir -p instance
uv run flask db upgrade
```

## Running the Application

### Start the web application

```bash
uv run python run.py
```

### Start the donation consumer

```bash
uv run python beer_consumer.py
```

## API Endpoints

### POST /donate
Records a new donation.

Request Body:
```json
{
  "date": "2023-12-01T10:00:00",
  "value": 100.5,
  "name": "Donor Name"
}
```

Response:
```json
{
  "message": "Success"
}
```

### GET /balance
Retrieves the total sum of all donations.

Response:
```json
{
  "Total": 1500.75
}
```

## Testing

The application includes a comprehensive test suite. To run the tests:

```bash
# Run all tests
make test

# Run tests with verbose output
make test-dev
```

The tests are located in the `tests/` directory and cover:
- Basic endpoint functionality
- Data validation
- Database operations
- Integration testing
