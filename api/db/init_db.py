import os, psycopg
from core.settings import settings

SCHEMA = open(os.path.join(os.path.dirname(__file__), "schema.sql"), "r", encoding="utf-8").read()

def init_db():
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()
    print("DB initialized")

if __name__ == "__main__":
    init_db()

