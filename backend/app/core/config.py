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