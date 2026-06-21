import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection


def add_discount_column():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE sales ADD COLUMN discount REAL DEFAULT 0")
        conn.commit()
        print("discount column added to sales table.")
    except Exception as e:
        print(f"Column may already exist: {e}")
    conn.close()


if __name__ == "__main__":
    add_discount_column()