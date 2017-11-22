from config import Config as config
if config.redis_password:
    REDIS_URL = 'redis://:{}@localhost:6379/{}'.format(
        config.redis_password,
        config.redis_db)
else:
    REDIS_URL = 'redis://localhost:6379/{}'.format(
        config.redis_db)
