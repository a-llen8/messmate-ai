import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    print("Subscriptions by status:")
    for row in conn.execute(text("SELECT status, count(*) FROM subscriptions GROUP BY status")):
        print(" ", row)

    print("\nActive subs with NULL end_date (open-ended):")
    print(" ", conn.execute(text("SELECT count(*) FROM subscriptions WHERE status='active' AND end_date IS NULL")).fetchone())

    print("\nActive subs still covering 2026-08-08, by plan_type:")
    for row in conn.execute(text("""
        SELECT plan_type, count(*)
        FROM subscriptions
        WHERE status = 'active' 
          AND (end_date IS NULL OR end_date >= '2026-08-08')
          AND start_date <= '2026-08-08'
        GROUP BY plan_type
    """)):
        print(" ", row)