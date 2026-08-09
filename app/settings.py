import os

from dotenv import load_dotenv

_ = load_dotenv()

# redis
redis_url: str = os.environ.get("REDIS_URL", "redis://127.0.0.1/2")
rabbit_url: str = os.environ.get("RABBIT_URL", "amqp://user:password@localhost:5672/")


# Beer consumer
BEER_URL: str = os.environ.get("BEER_URL", "http://127.0.0.1:6016/donate")
BEER_STAT = "bs_donats"
