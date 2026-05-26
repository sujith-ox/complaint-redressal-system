import os
import logging
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Required environment variables for DB connection
_REQUIRED_ENV = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME']

def get_engine():
    # FIX #18: validate all env vars are present before attempting connection
    missing = [v for v in _REQUIRED_ENV if not os.getenv(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {missing}. "
            f"Please set then in your .env file or environment."
        )

    schema = os.getenv('DB_SCHEMA', 'task')
    url = (
        f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        f"?options=-csearch_path%3D{schema}"
    )

    logger.info(
        f"Connecting to PostgreSQL at {os.getenv('DB_HOST')}:{os.getenv('DB_PORT')} "
        f"database={os.getenv('DB_NAME')} schema={schema}"
    )
    return create_engine(url)