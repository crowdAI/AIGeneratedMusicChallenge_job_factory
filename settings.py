from config import Config as config
REDIS_HOST = config.redis_host
REDIS_PORT = config.redis_port
if config.redis_password:
	REDIS_PASSWORD = config.redis_password
REDIS_DB = config.redis_db
