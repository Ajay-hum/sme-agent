from models import get_connection, create_tables
from datetime import datetime, timedelta
import random

def seed_data():
    conn = get_connection()
    cursor = conn.cursor()

    # Clear existing data so we can re-seed cleanly
    cursor.execute("DELETE FROM restock_log")
    cursor.execute("DELETE FROM sales")
    cursor.execute("DELETE FROM suppliers")
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM sqlite_sequence")  # reset auto-increment IDs

    # ── Products ────────────────────────────────────────────────────────────────
    products = [
        # (name, category, unit, current_stock, reorder_threshold, reorder_qty, unit_cost, selling_price)
        ("Dangote Rice 50kg",     "Grains",     "bag",    8,   10, 20, 42000, 47000),
        ("Semovita 1kg",          "Grains",     "pack",   45,  20, 50,  1200,  1500),
        ("Golden Penny Flour 1kg","Grains",     "pack",   6,   15, 40,   950,  1200),
        ("Titus Sardine (big)",   "Canned Food","carton", 12,  10, 15, 16000, 19500),
        ("Bournvita 900g",        "Beverages",  "tin",    3,   10, 20, 13500, 16000),
        ("Peak Milk (tin)",       "Beverages",  "carton", 18,  12, 24, 22000, 26000),
        ("Indomie Chicken 40pcs", "Noodles",    "carton", 22,  15, 30,  5800,  7000),
        ("Indomie Onion 40pcs",   "Noodles",    "carton", 7,   15, 30,  5600,  6800),
        ("Groundnut Oil 5L",      "Oils",       "gallon", 5,   8,  16, 11000, 13500),
        ("Palm Oil 25L",          "Oils",       "keg",    2,   5,  10, 28000, 33000),
        ("Omo Detergent 500g",    "Household",  "pack",   30,  20, 40,   950,  1200),
        ("Close-Up Toothpaste",   "Household",  "piece",  14,  12, 24,   650,   900),
        ("Nestle Milo 400g",      "Beverages",  "tin",    9,   10, 20, 11000, 13500),
        ("St. Louis Sugar 1kg",   "Grains",     "pack",   60,  25, 60,   700,   950),
        ("Vaseline 100ml",        "Personal",   "piece",  20,  15, 30,   800,  1100),
    ]

    cursor.executemany("""
        INSERT INTO products
            (name, category, unit, current_stock, reorder_threshold,
             reorder_quantity, unit_cost, selling_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, products)

    # ── Suppliers ───────────────────────────────────────────────────────────────
    suppliers = [
        # (name, phone, product_id, lead_time_days)
        ("Alhaji Musa Grains",      "08031234567", 1,  2),
        ("Alhaji Musa Grains",      "08031234567", 2,  2),
        ("Alhaji Musa Grains",      "08031234567", 3,  2),
        ("Balogun Market Wholesale","08059876543", 4,  1),
        ("Balogun Market Wholesale","08059876543", 5,  1),
        ("Leventis Foods Ltd",      "07012345678", 6,  3),
        ("Noodles Direct Lagos",    "09087654321", 7,  1),
        ("Noodles Direct Lagos",    "09087654321", 8,  1),
        ("Kano Oil Traders",        "08112345678", 9,  3),
        ("Kano Oil Traders",        "08112345678", 10, 3),
        ("Consumer Goods Ltd",      "07098765432", 11, 2),
        ("Consumer Goods Ltd",      "07098765432", 12, 2),
        ("Nestle Nigeria Dist.",    "08023456789", 13, 4),
        ("Sugar & Grains Co.",      "08134567890", 14, 1),
        ("Unilever Distributors",   "07145678901", 15, 2),
    ]

    cursor.executemany("""
        INSERT INTO suppliers (name, phone, product_id, lead_time_days)
        VALUES (?, ?, ?, ?)
    """, suppliers)

    # ── Sales (last 30 days) ─────────────────────────────────────────────────
    # Simulate realistic daily sales with some randomness
    today = datetime.today()
    sales = []

    # Each product has a base daily sales rate
    daily_sales_rate = {
        1: (0.5, 1.5),   # Rice — sells 0.5–1.5 bags/day
        2: (2, 6),        # Semovita
        3: (1, 4),        # Flour
        4: (0.3, 1),      # Sardine
        5: (0.5, 2),      # Bournvita
        6: (0.5, 1.5),   # Peak Milk
        7: (1, 4),        # Indomie Chicken
        8: (1, 3),        # Indomie Onion
        9: (0.3, 1),      # Groundnut Oil
        10: (0.2, 0.8),   # Palm Oil
        11: (1, 3),       # Omo
        12: (1, 3),       # Toothpaste
        13: (0.5, 2),     # Milo
        14: (3, 8),       # Sugar
        15: (1, 3),       # Vaseline
    }

    for product_id, (low, high) in daily_sales_rate.items():
        # Get selling price for revenue calculation
        cursor.execute("SELECT selling_price FROM products WHERE id=?", (product_id,))
        price = cursor.fetchone()[0]

        for day_offset in range(30):
            sale_date = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            # Some days have no sales (realistic)
            if random.random() < 0.2:
                continue
            qty = round(random.uniform(low, high), 1)
            revenue = round(qty * price, 2)
            sales.append((product_id, qty, sale_date, revenue))

    cursor.executemany("""
        INSERT INTO sales (product_id, quantity_sold, sale_date, revenue)
        VALUES (?, ?, ?, ?)
    """, sales)

    # ── Restock log (last 30 days) ──────────────────────────────────────────
    restock_entries = [
        (1,  20, (today - timedelta(days=20)).strftime("%Y-%m-%d"), 840000, 1),
        (7,  30, (today - timedelta(days=15)).strftime("%Y-%m-%d"), 174000, 7),
        (8,  30, (today - timedelta(days=15)).strftime("%Y-%m-%d"), 168000, 8),
        (14, 60, (today - timedelta(days=10)).strftime("%Y-%m-%d"),  42000, 14),
        (11, 40, (today - timedelta(days=8)).strftime("%Y-%m-%d"),   38000, 11),
        (6,  24, (today - timedelta(days=5)).strftime("%Y-%m-%d"),  528000, 6),
    ]

    cursor.executemany("""
        INSERT INTO restock_log
            (product_id, quantity_added, restock_date, cost, supplier_id)
        VALUES (?, ?, ?, ?, ?)
    """, restock_entries)

    conn.commit()
    conn.close()
    print("Database seeded successfully.")
    print(f"  {len(products)} products")
    print(f"  {len(suppliers)} supplier records")
    print(f"  {len(sales)} sales records")
    print(f"  {len(restock_entries)} restock entries")


if __name__ == "__main__":
    create_tables()
    seed_data()