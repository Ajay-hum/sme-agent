import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection


def create_auth_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Businesses table — one row per company using the app
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            business_type TEXT DEFAULT 'provisions',
            created_at    TEXT DEFAULT (date('now'))
        )
    """)

    # Users table — people who log into the app
    # A business can have multiple users (owner, staff, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id   INTEGER NOT NULL,
            full_name     TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT DEFAULT 'owner',
            created_at    TEXT DEFAULT (date('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        )
    """)

    # Add business_id to products table if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN business_id INTEGER DEFAULT 1")
    except Exception:
        pass  # Column already exists — that's fine

    # Add business_id to sales table if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE sales ADD COLUMN business_id INTEGER DEFAULT 1")
    except Exception:
        pass

    # Add business_id to restock_log table if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE restock_log ADD COLUMN business_id INTEGER DEFAULT 1")
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("Auth tables created successfully.")


def create_default_business():
    """
    Creates a default business (id=1) and assigns all existing
    seed data to it. This preserves test data when adding auth.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if default business already exists
    cursor.execute("SELECT id FROM businesses WHERE id = 1")
    if cursor.fetchone():
        conn.close()
        print("Default business already exists.")
        return

    cursor.execute("""
        INSERT INTO businesses (id, name, email, business_type)
        VALUES (1, 'Demo Store', 'demo@ogaassistant.com', 'provisions')
    """)

    conn.commit()
    conn.close()
    print("Default business created.")


if __name__ == "__main__":
    create_auth_tables()
    create_default_business()