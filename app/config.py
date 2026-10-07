import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./geo.db")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
