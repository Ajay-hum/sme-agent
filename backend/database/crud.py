import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection
from datetime import datetime


def get_all_products() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY category, name")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product_by_name(name: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM products WHERE LOWER(name) LIKE LOWER(?)",
        (f"%{name}%",)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_product_by_id(product_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_product(data: dict) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products
            (name, category, unit, current_stock, reorder_threshold,
             reorder_quantity, unit_cost, selling_price)
        VALUES (:name, :category, :unit, :current_stock, :reorder_threshold,
                :reorder_quantity, :unit_cost, :selling_price)
    """, data)
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return get_product_by_id(product_id)


def update_product_stock(product_id: int, new_stock: float) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE products SET current_stock = ? WHERE id = ?",
        (new_stock, product_id)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def record_sale(product_id: int, quantity: float, revenue: float) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.today().strftime("%Y-%m-%d")
    cursor.execute("""
        INSERT INTO sales (product_id, quantity_sold, sale_date, revenue)
        VALUES (?, ?, ?, ?)
    """, (product_id, quantity, today, revenue))
    cursor.execute("""
        UPDATE products SET current_stock = MAX(0, current_stock - ?) WHERE id = ?
    """, (quantity, product_id))
    conn.commit()
    sale_id = cursor.lastrowid
    conn.close()
    return {"id": sale_id, "product_id": product_id,
            "quantity_sold": quantity, "sale_date": today, "revenue": revenue}


def get_sales_summary(days: int = 7) -> list[dict]:
    from datetime import timedelta
    conn = get_connection()
    cursor = conn.cursor()
    since = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT p.name, p.unit,
               SUM(s.quantity_sold) AS total_sold,
               SUM(s.revenue) AS total_revenue
        FROM sales s
        JOIN products p ON p.id = s.product_id
        WHERE s.sale_date >= ?
        GROUP BY p.id
        ORDER BY total_revenue DESC
    """, (since,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_supplier_for_product(product_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM suppliers WHERE product_id = ? LIMIT 1", (product_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def log_restock(product_id: int, quantity: float,
                cost: float, supplier_id: int = None) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.today().strftime("%Y-%m-%d")
    cursor.execute("""
        INSERT INTO restock_log (product_id, quantity_added, restock_date, cost, supplier_id)
        VALUES (?, ?, ?, ?, ?)
    """, (product_id, quantity, today, cost, supplier_id))
    cursor.execute(
        "UPDATE products SET current_stock = current_stock + ? WHERE id = ?",
        (quantity, product_id)
    )
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()
    return {"id": entry_id, "product_id": product_id,
            "quantity_added": quantity, "restock_date": today, "cost": cost}


def get_restock_history(product_id: int = None) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if product_id:
        cursor.execute("""
            SELECT r.*, p.name AS product_name, s.name AS supplier_name
            FROM restock_log r
            JOIN products p ON p.id = r.product_id
            LEFT JOIN suppliers s ON s.id = r.supplier_id
            WHERE r.product_id = ? ORDER BY r.restock_date DESC
        """, (product_id,))
    else:
        cursor.execute("""
            SELECT r.*, p.name AS product_name, s.name AS supplier_name
            FROM restock_log r
            JOIN products p ON p.id = r.product_id
            LEFT JOIN suppliers s ON s.id = r.supplier_id
            ORDER BY r.restock_date DESC LIMIT 50
        """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]