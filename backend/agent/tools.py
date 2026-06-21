import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection
from datetime import datetime, timedelta


def check_stock(business_id: int, product_name: str = None) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if product_name:
        cursor.execute("""
            SELECT name, category, unit, current_stock,
                   reorder_threshold, selling_price
            FROM products
            WHERE LOWER(name) LIKE LOWER(?) AND business_id = ?
        """, (f"%{product_name}%", business_id))
    else:
        cursor.execute("""
            SELECT name, category, unit, current_stock,
                   reorder_threshold, selling_price
            FROM products WHERE business_id = ?
            ORDER BY category, name
        """, (business_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_low_stock_alerts(business_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, p.category, p.unit,
               p.current_stock, p.reorder_threshold,
               p.reorder_quantity, p.unit_cost,
               s.name AS supplier_name,
               s.phone AS supplier_phone,
               s.lead_time_days
        FROM products p
        LEFT JOIN suppliers s ON s.product_id = p.id
        WHERE p.current_stock <= p.reorder_threshold
          AND p.business_id = ?
        ORDER BY (p.current_stock - p.reorder_threshold) ASC
    """, (business_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sales_history(business_id: int,
                      product_name: str = None, days: int = 7) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    if product_name:
        cursor.execute("""
            SELECT p.name AS product, p.unit,
                   SUM(s.quantity_sold) AS total_sold,
                   SUM(s.revenue) AS total_revenue,
                   COUNT(s.id) AS num_transactions
            FROM sales s JOIN products p ON p.id = s.product_id
            WHERE s.sale_date >= ? AND s.business_id = ?
              AND LOWER(p.name) LIKE LOWER(?)
            GROUP BY p.id
        """, (since_date, business_id, f"%{product_name}%"))
    else:
        cursor.execute("""
            SELECT p.name AS product, p.unit,
                   SUM(s.quantity_sold) AS total_sold,
                   SUM(s.revenue) AS total_revenue,
                   COUNT(s.id) AS num_transactions
            FROM sales s JOIN products p ON p.id = s.product_id
            WHERE s.sale_date >= ? AND s.business_id = ?
            GROUP BY p.id ORDER BY total_revenue DESC
        """, (since_date, business_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_reorder_suggestions(business_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.today() - timedelta(days=14)).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT p.id, p.name, p.unit, p.current_stock,
               p.reorder_threshold, p.reorder_quantity, p.unit_cost,
               s.name AS supplier_name, s.phone AS supplier_phone,
               s.lead_time_days,
               COALESCE(SUM(sl.quantity_sold), 0) AS total_sold_14_days,
               COALESCE(COUNT(DISTINCT sl.sale_date), 1) AS days_with_sales
        FROM products p
        LEFT JOIN suppliers s ON s.product_id = p.id
        LEFT JOIN sales sl ON sl.product_id = p.id
              AND sl.sale_date >= ? AND sl.business_id = ?
        WHERE p.current_stock <= p.reorder_threshold AND p.business_id = ?
        GROUP BY p.id
    """, (since_date, business_id, business_id))
    rows = cursor.fetchall()
    conn.close()
    suggestions = []
    for row in rows:
        r = dict(row)
        avg_daily = round(r["total_sold_14_days"] / 14, 2)
        days_left = round(r["current_stock"] / avg_daily, 1) if avg_daily > 0 else "unknown"
        suggested_qty = max(r["reorder_quantity"], round(avg_daily * 14))
        estimated_cost = round(suggested_qty * r["unit_cost"], 2)
        suggestions.append({
            "product": r["name"], "unit": r["unit"],
            "current_stock": r["current_stock"], "days_left": days_left,
            "avg_daily_sales": avg_daily, "suggested_order_qty": suggested_qty,
            "estimated_cost_naira": estimated_cost,
            "supplier": r["supplier_name"], "supplier_phone": r["supplier_phone"],
            "lead_time_days": r["lead_time_days"],
        })
    suggestions.sort(key=lambda x: float(x["days_left"]) if x["days_left"] != "unknown" else 0)
    return suggestions


def update_stock(business_id: int, product_name: str,
                 quantity_added: float, supplier_name: str = None) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, current_stock, unit_cost FROM products
        WHERE LOWER(name) LIKE LOWER(?) AND business_id = ?
    """, (f"%{product_name}%", business_id))
    product = cursor.fetchone()
    if not product:
        conn.close()
        return {"error": f"Product '{product_name}' not found."}
    product = dict(product)
    new_stock = product["current_stock"] + quantity_added
    cursor.execute("UPDATE products SET current_stock = ? WHERE id = ?",
                   (new_stock, product["id"]))
    today = datetime.today().strftime("%Y-%m-%d")
    cost = round(quantity_added * product["unit_cost"], 2)
    cursor.execute("""
        INSERT INTO restock_log (product_id, quantity_added, restock_date, cost, business_id)
        VALUES (?, ?, ?, ?, ?)
    """, (product["id"], quantity_added, today, cost, business_id))
    conn.commit()
    conn.close()
    return {
        "success": True, "product": product["name"],
        "quantity_added": quantity_added, "new_stock_level": new_stock,
        "estimated_cost_naira": cost, "date": today,
    }


TOOLS = [
    {
        "name": "check_stock",
        "description": "Get current stock levels for one or all products. Use when the owner asks how much of something is left.",
        "input_schema": {"type": "object", "properties": {"product_name": {"type": "string", "description": "Name or partial name. Leave empty for all."}}, "required": []},
    },
    {
        "name": "get_low_stock_alerts",
        "description": "Returns all products running low. Use when owner asks what needs restocking.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_sales_history",
        "description": "Returns sales data for the last N days. Use when asked about sales performance or revenue.",
        "input_schema": {"type": "object", "properties": {"product_name": {"type": "string", "description": "Filter to a specific product. Leave empty for all."}, "days": {"type": "integer", "description": "How many days back to look. Default is 7."}}, "required": []},
    },
    {
        "name": "get_reorder_suggestions",
        "description": "Calculates smart reorder suggestions for all low-stock products with supplier info and Naira costs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_stock",
        "description": "Records new stock arriving. Use when owner says they received or bought new stock.",
        "input_schema": {"type": "object", "properties": {"product_name": {"type": "string", "description": "Name of the product being restocked."}, "quantity_added": {"type": "number", "description": "How many units were added."}, "supplier_name": {"type": "string", "description": "Who supplied it (optional)."}}, "required": ["product_name", "quantity_added"]},
    },
]


def run_tool(tool_name: str, tool_input: dict, business_id: int = 1):
    if tool_name == "check_stock":
        return check_stock(business_id, **tool_input)
    elif tool_name == "get_low_stock_alerts":
        return get_low_stock_alerts(business_id)
    elif tool_name == "get_sales_history":
        return get_sales_history(business_id, **tool_input)
    elif tool_name == "get_reorder_suggestions":
        return get_reorder_suggestions(business_id)
    elif tool_name == "update_stock":
        return update_stock(business_id, **tool_input)
    else:
        return {"error": f"Unknown tool: {tool_name}"}