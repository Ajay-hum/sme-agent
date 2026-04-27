import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "sme.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Products table — every item the business sells or stocks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            unit TEXT,                -- e.g. "bag", "carton", "piece"
            current_stock REAL DEFAULT 0,
            reorder_threshold REAL DEFAULT 10,  -- alert when stock drops below this
            reorder_quantity REAL DEFAULT 50,   -- how much to order when restocking
            unit_cost REAL DEFAULT 0,           -- what you buy it for
            selling_price REAL DEFAULT 0        -- what you sell it for
        )
    """)

    # Suppliers table — who you buy from
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            product_id INTEGER,
            lead_time_days INTEGER DEFAULT 1,   -- how many days to deliver
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # Sales table — every sale recorded
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity_sold REAL NOT NULL,
            sale_date TEXT NOT NULL,            -- stored as YYYY-MM-DD
            revenue REAL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # Restock log — every time stock was added
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restock_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity_added REAL NOT NULL,
            restock_date TEXT NOT NULL,
            cost REAL,
            supplier_id INTEGER,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    conn.commit()
    conn.close()
    print("Tables created successfully.")


if __name__ == "__main__":
    create_tables()