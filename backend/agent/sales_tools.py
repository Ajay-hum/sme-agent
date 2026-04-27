import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection
from datetime import datetime


# ── Tool 1: Check product availability ───────────────────────────────────────
def check_availability(product_name: str, quantity_needed: float = 1) -> dict:
    """
    Checks if a product is available and if the requested quantity can be met.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, category, unit, current_stock, selling_price
        FROM products
        WHERE LOWER(name) LIKE LOWER(?)
        ORDER BY current_stock DESC
    """, (f"%{product_name}%",))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {
            "found": False,
            "product_name": product_name,
            "message": f"We don't carry '{product_name}' in this store.",
        }

    results = []
    for row in rows:
        r = dict(row)
        can_fulfil = r["current_stock"] >= quantity_needed
        results.append({
            "id":             r["id"],
            "name":           r["name"],
            "category":       r["category"],
            "unit":           r["unit"],
            "current_stock":  r["current_stock"],
            "selling_price":  r["selling_price"],
            "quantity_needed": quantity_needed,
            "can_fulfil":     can_fulfil,
            "stock_status":   "available" if r["current_stock"] > 0 else "out of stock",
        })

    return {"found": True, "matches": results}


# ── Tool 2: Get product price ─────────────────────────────────────────────────
def get_price(product_name: str) -> list[dict]:
    """
    Returns the selling price for a product or list of products matching
    the search term.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, category, unit, selling_price, current_stock
        FROM products
        WHERE LOWER(name) LIKE LOWER(?)
        ORDER BY name
    """, (f"%{product_name}%",))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return [{"error": f"No products found matching '{product_name}'."}]

    return [dict(r) for r in rows]


# ── Tool 3: Search products by name or category ───────────────────────────────
def search_products(query: str) -> list[dict]:
    """
    Searches products by name or category.
    Useful when customer asks broad questions like
    'what oils do you have?' or 'show me your beverages'.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, category, unit, selling_price, current_stock
        FROM products
        WHERE LOWER(name)     LIKE LOWER(?)
        OR LOWER(category) LIKE LOWER(?)
        OR (LOWER(?) LIKE '%oil%'     AND LOWER(category) = 'oils')
        OR (LOWER(?) LIKE '%beverage%' AND LOWER(category) = 'beverages')
        OR (LOWER(?) LIKE '%drink%'   AND LOWER(category) = 'beverages')
        OR (LOWER(?) LIKE '%noodle%'  AND LOWER(category) = 'noodles')
        OR (LOWER(?) LIKE '%pasta%'   AND LOWER(category) = 'noodles')
        OR (LOWER(?) LIKE '%grain%'   AND LOWER(category) = 'grains')
        ORDER BY category, name
    """, (f"%{query}%", f"%{query}%", query, query, query, query, query, query))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return [{"message": f"No products found for '{query}'."}]

    return [dict(r) for r in rows]


# ── Tool 4: Record a confirmed sale ──────────────────────────────────────────
def record_sale(product_name: str, quantity: float) -> dict:
    """
    Records a confirmed sale — deducts from stock and logs the transaction.
    Only call this after the customer has explicitly confirmed they want to buy.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Find the product
    cursor.execute("""
        SELECT id, name, unit, current_stock, selling_price
        FROM products
        WHERE LOWER(name) LIKE LOWER(?)
    """, (f"%{product_name}%",))

    product = cursor.fetchone()
    if not product:
        conn.close()
        return {"success": False, "error": f"Product '{product_name}' not found."}

    product = dict(product)

    # Check we have enough stock
    if product["current_stock"] < quantity:
        conn.close()
        return {
            "success":       False,
            "error":         "Insufficient stock.",
            "requested":     quantity,
            "available":     product["current_stock"],
            "product":       product["name"],
        }

    revenue      = round(quantity * product["selling_price"], 2)
    new_stock    = round(product["current_stock"] - quantity, 2)
    today        = datetime.today().strftime("%Y-%m-%d")

    # Deduct stock
    cursor.execute("""
        UPDATE products SET current_stock = ? WHERE id = ?
    """, (new_stock, product["id"]))

    # Log the sale
    cursor.execute("""
        INSERT INTO sales (product_id, quantity_sold, sale_date, revenue)
        VALUES (?, ?, ?, ?)
    """, (product["id"], quantity, today, revenue))

    conn.commit()
    conn.close()

    return {
        "success":         True,
        "product":         product["name"],
        "quantity_sold":   quantity,
        "unit":            product["unit"],
        "revenue":         revenue,
        "price_per_unit":  product["selling_price"],
        "remaining_stock": new_stock,
        "date":            today,
    }


# ── Tool registry ─────────────────────────────────────────────────────────────
SALES_TOOLS = [
    {
        "name": "check_availability",
        "description": (
            "Checks if a product is in stock and whether a specific quantity "
            "can be fulfilled. Use when a customer asks if something is available "
            "or wants to buy a specific quantity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Name or partial name of the product.",
                },
                "quantity_needed": {
                    "type": "number",
                    "description": "How many units the customer wants. Default 1.",
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "get_price",
        "description": (
            "Returns the selling price of a product in Naira. "
            "Use when a customer asks how much something costs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Name or partial name of the product.",
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "search_products",
        "description": (
            "Searches products by name or category. Use when a customer asks "
            "broad questions like 'what oils do you have?' or "
            "'show me your beverages' or 'what noodles do you sell?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term — product name or category.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "record_sale",
        "description": (
            "Records a confirmed sale and deducts from stock. "
            "ONLY call this after the customer has explicitly confirmed "
            "they want to buy. Never record a sale speculatively."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Name of the product being sold.",
                },
                "quantity": {
                    "type": "number",
                    "description": "Number of units sold.",
                },
            },
            "required": ["product_name", "quantity"],
        },
    },
]


# ── Tool dispatcher ───────────────────────────────────────────────────────────
def run_sales_tool(tool_name: str, tool_input: dict):
    if tool_name == "check_availability":
        return check_availability(**tool_input)
    elif tool_name == "get_price":
        return get_price(**tool_input)
    elif tool_name == "search_products":
        return search_products(**tool_input)
    elif tool_name == "record_sale":
        return record_sale(**tool_input)
    else:
        return {"error": f"Unknown tool: {tool_name}"}