from app.core.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text("ALTER TABLE subscription_requests DROP CONSTRAINT IF EXISTS idx_one_pending_new"))

print("Dropped (if it existed)")
