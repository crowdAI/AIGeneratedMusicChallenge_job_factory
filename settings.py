from config import Config as config
REDIS_URL = 'redis://:{}@localhost:6379/{}'.format(
    config.redis_password,
    config.redis_db)
