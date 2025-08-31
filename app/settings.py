import os
from dotenv import load_dotenv

_ = load_dotenv()

# redis
redis_url: str = os.environ.get('REDIS_URL', 'redis://127.0.0.1/2')

# Beer consumer
BEER_URL: str = os.environ.get('BEER_URL', 'http://127.0.0.1:6016/donate')
BEER_STAT = 'bs_donats'

currencies: dict[str, float] = {
    'USD': 80,
    'RUB': 1,
    'EUR': 90,
    'POINTS': 1,
}


