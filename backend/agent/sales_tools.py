import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection
from datetime import datetime


def check_availability(business_id: int, product_name: str,
                       quantity_needed: float = 1) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, category, unit, current_stock, selling_price
        FROM products
        WHERE LOWER(name) LIKE LOWER(?) AND business_id = ?
        ORDER BY current_stock DESC
    """, (f"%{product_name}%", business_id))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"found": False, "product_name": product_name,
                "message": f"We don't carry '{product_name}' in this store."}

    results = []
    for row in rows:
        r = dict(row)
        can_fulfil = r["current_stock"] >= quantity_needed
        results.append({
            "id": r["id"], "name": r["name"], "category": r["category"],
            "unit": r["unit"], "current_stock": r["current_stock"],
            "selling_price": r["selling_price"],
            "quantity_needed": quantity_needed, "can_fulfil": can_fulfil,
            "stock_status": "available" if r["current_stock"] > 0 else "out of stock",
        })
    return {"found": True, "matches": results}


def get_price(business_id: int, product_name: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, category, unit, selling_price, current_stock
        FROM products
        WHERE LOWER(name) LIKE LOWER(?) AND business_id = ?
        ORDER BY name
    """, (f"%{product_name}%", business_id))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return [{"error": f"No products found matching '{product_name}'."}]
    return [dict(r) for r in rows]


def search_products(business_id: int, query: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, category, unit, selling_price, current_stock
        FROM products
        WHERE (LOWER(name) LIKE LOWER(?) OR LOWER(category) LIKE LOWER(?))
          AND business_id = ?
        ORDER BY category, name
    """, (f"%{query}%", f"%{query}%", business_id))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return [{"message": f"No products found for '{query}'."}]
    return [dict(r) for r in rows]


def record_sale(business_id: int, product_name: str, quantity: float) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, unit, current_stock, selling_price
        FROM products
        WHERE LOWER(name) LIKE LOWER(?) AND business_id = ?
    """, (f"%{product_name}%", business_id))
    product = cursor.fetchone()
    if not product:
        conn.close()
        return {"success": False, "error": f"Product '{product_name}' not found."}

    product = dict(product)
    if product["current_stock"] < quantity:
        conn.close()
        return {"success": False, "error": "Insufficient stock.",
                "requested": quantity, "available": product["current_stock"],
                "product": product["name"]}

    revenue   = round(quantity * product["selling_price"], 2)
    new_stock = round(product["current_stock"] - quantity, 2)
    today     = datetime.today().strftime("%Y-%m-%d")

    cursor.execute("UPDATE products SET current_stock = ? WHERE id = ?",
                   (new_stock, product["id"]))
    cursor.execute("""
        INSERT INTO sales (product_id, quantity_sold, sale_date, revenue, business_id)
        VALUES (?, ?, ?, ?, ?)
    """, (product["id"], quantity, today, revenue, business_id))

    conn.commit()
    conn.close()
    return {
        "success": True, "product": product["name"],
        "quantity_sold": quantity, "unit": product["unit"],
        "revenue": revenue, "price_per_unit": product["selling_price"],
        "remaining_stock": new_stock, "date": today,
    }


SALES_TOOLS = [
    {"name": "check_availability", "description": "Checks if a product is in stock and whether a specific quantity can be fulfilled.", "input_schema": {"type": "object", "properties": {"product_name": {"type": "string", "description": "Name or partial name of the product."}, "quantity_needed": {"type": "number", "description": "How many units the customer wants. Default 1."}}, "required": ["product_name"]}},
    {"name": "get_price", "description": "Returns the selling price of a product in Naira.", "input_schema": {"type": "object", "properties": {"product_name": {"type": "string", "description": "Name or partial name of the product."}}, "required": ["product_name"]}},
    {"name": "search_products", "description": "Searches products by name or category. Use for broad questions like 'what oils do you have?'", "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "Search term — product name or category."}}, "required": ["query"]}},
    {"name": "record_sale", "description": "Records a confirmed sale. ONLY call after the customer has explicitly confirmed they want to buy.", "input_schema": {"type": "object", "properties": {"product_name": {"type": "string", "description": "Name of the product being sold."}, "quantity": {"type": "number", "description": "Number of units sold."}}, "required": ["product_name", "quantity"]}},
]


def run_sales_tool(tool_name: str, tool_input: dict, business_id: int = 1):
    if tool_name == "check_availability":
        return check_availability(business_id, **tool_input)
    elif tool_name == "get_price":
        return get_price(business_id, **tool_input)
    elif tool_name == "search_products":
        return search_products(business_id, **tool_input)
    elif tool_name == "record_sale":
        return record_sale(business_id, **tool_input)
    else:
        return {"error": f"Unknown tool: {tool_name}"}