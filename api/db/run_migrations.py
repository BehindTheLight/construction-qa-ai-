import os, glob, psycopg
from psycopg.rows import tuple_row
from core.settings import settings

def run():
    with psycopg.connect(settings.POSTGRES_DSN, row_factory=tuple_row) as conn:
        cur = conn.cursor()
        for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "migrations", "*.sql"))):
            print(f"Running migration: {os.path.basename(path)}")
            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()
            cur.execute(sql)
        conn.commit()
        print("✅ migrations applied")

if __name__ == "__main__":
    run()


