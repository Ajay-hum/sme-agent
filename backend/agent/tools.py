import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection
from datetime import datetime, timedelta


# ── Tool 1: Check stock levels ───────────────────────────────────────────────
def check_stock(product_name: str = None) -> list[dict]:
    """
    Returns current stock levels.
    If product_name is given, returns that product only.
    If product_name is None, returns all products.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if product_name:
        cursor.execute("""
            SELECT name, category, unit, current_stock,
                   reorder_threshold, selling_price
            FROM products
            WHERE LOWER(name) LIKE LOWER(?)
        """, (f"%{product_name}%",))
    else:
        cursor.execute("""
            SELECT name, category, unit, current_stock,
                   reorder_threshold, selling_price
            FROM products
            ORDER BY category, name
        """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ── Tool 2: Get low stock alerts ─────────────────────────────────────────────
def get_low_stock_alerts() -> list[dict]:
    """
    Returns all products where current stock is at or below reorder threshold.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            p.name,
            p.category,
            p.unit,
            p.current_stock,
            p.reorder_threshold,
            p.reorder_quantity,
            p.unit_cost,
            s.name AS supplier_name,
            s.phone AS supplier_phone,
            s.lead_time_days
        FROM products p
        LEFT JOIN suppliers s ON s.product_id = p.id
        WHERE p.current_stock <= p.reorder_threshold
        ORDER BY (p.current_stock - p.reorder_threshold) ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ── Tool 3: Get sales history ─────────────────────────────────────────────────
def get_sales_history(product_name: str = None, days: int = 7) -> list[dict]:
    """
    Returns sales records for the last N days.
    If product_name given, filters to that product.
    """
    conn = get_connection()
    cursor = conn.cursor()

    since_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    if product_name:
        cursor.execute("""
            SELECT
                p.name AS product,
                p.unit,
                SUM(s.quantity_sold) AS total_sold,
                SUM(s.revenue)       AS total_revenue,
                COUNT(s.id)          AS num_transactions
            FROM sales s
            JOIN products p ON p.id = s.product_id
            WHERE s.sale_date >= ?
              AND LOWER(p.name) LIKE LOWER(?)
            GROUP BY p.id
        """, (since_date, f"%{product_name}%"))
    else:
        cursor.execute("""
            SELECT
                p.name AS product,
                p.unit,
                SUM(s.quantity_sold) AS total_sold,
                SUM(s.revenue)       AS total_revenue,
                COUNT(s.id)          AS num_transactions
            FROM sales s
            JOIN products p ON p.id = s.product_id
            WHERE s.sale_date >= ?
            GROUP BY p.id
            ORDER BY total_revenue DESC
        """, (since_date,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ── Tool 4: Get reorder suggestions ──────────────────────────────────────────
def get_reorder_suggestions() -> list[dict]:
    """
    For each low-stock product, calculates how much to reorder based on
    average daily sales velocity over the last 14 days.
    Returns actionable suggestions with supplier contact info.
    """
    conn = get_connection()
    cursor = conn.cursor()

    since_date = (datetime.today() - timedelta(days=14)).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT
            p.id,
            p.name,
            p.unit,
            p.current_stock,
            p.reorder_threshold,
            p.reorder_quantity,
            p.unit_cost,
            s.name        AS supplier_name,
            s.phone       AS supplier_phone,
            s.lead_time_days,
            COALESCE(SUM(sl.quantity_sold), 0) AS total_sold_14_days,
            COALESCE(COUNT(DISTINCT sl.sale_date), 1) AS days_with_sales
        FROM products p
        LEFT JOIN suppliers s ON s.product_id = p.id
        LEFT JOIN sales sl
               ON sl.product_id = p.id
              AND sl.sale_date >= ?
        WHERE p.current_stock <= p.reorder_threshold
        GROUP BY p.id
    """, (since_date,))

    rows = cursor.fetchall()
    conn.close()

    suggestions = []
    for row in rows:
        r = dict(row)

        # Average daily sales
        avg_daily = round(r["total_sold_14_days"] / 14, 2)

        # Days of stock left
        days_left = (
            round(r["current_stock"] / avg_daily, 1)
            if avg_daily > 0 else "unknown"
        )

        # Suggested order quantity — whichever is larger:
        # the standard reorder qty, or 14 days worth of sales
        suggested_qty = max(
            r["reorder_quantity"],
            round(avg_daily * 14)
        )

        estimated_cost = round(suggested_qty * r["unit_cost"], 2)

        suggestions.append({
            "product":         r["name"],
            "unit":            r["unit"],
            "current_stock":   r["current_stock"],
            "days_left":       days_left,
            "avg_daily_sales": avg_daily,
            "suggested_order_qty": suggested_qty,
            "estimated_cost_naira": estimated_cost,
            "supplier":        r["supplier_name"],
            "supplier_phone":  r["supplier_phone"],
            "lead_time_days":  r["lead_time_days"],
        })

    # Sort by most urgent (fewest days left)
    suggestions.sort(
        key=lambda x: float(x["days_left"]) if x["days_left"] != "unknown" else 0
    )

    return suggestions


# ── Tool 5: Update stock level ────────────────────────────────────────────────
def update_stock(product_name: str, quantity_added: float,
                 supplier_name: str = None) -> dict:
    """
    Records a restock event — adds quantity to current stock
    and logs it in restock_log.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Find the product
    cursor.execute("""
        SELECT id, name, current_stock, unit_cost
        FROM products
        WHERE LOWER(name) LIKE LOWER(?)
    """, (f"%{product_name}%",))

    product = cursor.fetchone()
    if not product:
        conn.close()
        return {"error": f"Product '{product_name}' not found."}

    product = dict(product)
    new_stock = product["current_stock"] + quantity_added

    # Update the stock level
    cursor.execute("""
        UPDATE products SET current_stock = ? WHERE id = ?
    """, (new_stock, product["id"]))

    # Log the restock
    today = datetime.today().strftime("%Y-%m-%d")
    cost = round(quantity_added * product["unit_cost"], 2)

    cursor.execute("""
        INSERT INTO restock_log
            (product_id, quantity_added, restock_date, cost)
        VALUES (?, ?, ?, ?)
    """, (product["id"], quantity_added, today, cost))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "product": product["name"],
        "quantity_added": quantity_added,
        "new_stock_level": new_stock,
        "estimated_cost_naira": cost,
        "date": today,
    }


# ── Tool registry (used by the agent) ────────────────────────────────────────
# This is the list of tools we hand to Claude so it knows what it can call.
TOOLS = [
    {
        "name": "check_stock",
        "description": (
            "Get current stock levels for one or all products. "
            "Use when the owner asks how much of something is left, "
            "or wants to see all stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": (
                        "Name or partial name of the product to check. "
                        "Leave empty to get all products."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_low_stock_alerts",
        "description": (
            "Returns all products that are running low — "
            "at or below their reorder threshold. "
            "Use when owner asks what's running low or needs restocking."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_sales_history",
        "description": (
            "Returns sales data for the last N days. "
            "Use when asked about sales performance, revenue, "
            "or how fast a product is selling."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Filter to a specific product. Leave empty for all.",
                },
                "days": {
                    "type": "integer",
                    "description": "How many days back to look. Default is 7.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_reorder_suggestions",
        "description": (
            "Calculates smart reorder suggestions for all low-stock products "
            "based on recent sales velocity. Includes supplier contact info "
            "and estimated cost in Naira. Use when owner asks what to order "
            "or what to buy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "update_stock",
        "description": (
            "Records new stock arriving — updates the product's stock level "
            "and logs the restock event. Use when owner says they received "
            "or bought new stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Name of the product being restocked.",
                },
                "quantity_added": {
                    "type": "number",
                    "description": "How many units were added.",
                },
                "supplier_name": {
                    "type": "string",
                    "description": "Who supplied it (optional).",
                },
            },
            "required": ["product_name", "quantity_added"],
        },
    },
]


# ── Tool dispatcher ───────────────────────────────────────────────────────────
# When Claude decides to call a tool, this function runs the right one.
def run_tool(tool_name: str, tool_input: dict):
    if tool_name == "check_stock":
        return check_stock(**tool_input)
    elif tool_name == "get_low_stock_alerts":
        return get_low_stock_alerts()
    elif tool_name == "get_sales_history":
        return get_sales_history(**tool_input)
    elif tool_name == "get_reorder_suggestions":
        return get_reorder_suggestions()
    elif tool_name == "update_stock":
        return update_stock(**tool_input)
    else:
        return {"error": f"Unknown tool: {tool_name}"}