from datetime import time

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    GEMINI_API_KEY: str
    QR_SECRET: str
    QR_SEMESTER: str
    DB_USER: str
    DB_PASS: str

    class Config:
        env_file = "../.env"


settings = Settings()

SLOT_WINDOWS = {
    "breakfast": (time(7, 0), time(10, 0)),
    "lunch": (time(12, 0), time(14, 30)),
    "dinner": (time(19, 0), time(21, 30)),
}

PLAN_SLOTS = {
    "full": {"breakfast", "lunch", "dinner"},
    "breakfast_only": {"breakfast"},
    "lunch_only": {"lunch"},
    "dinner_only": {"dinner"},
    "breakfast_lunch": {"breakfast", "lunch"},
    "breakfast_dinner": {"breakfast", "dinner"},
    "lunch_dinner": {"lunch", "dinner"},
}