import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection
from datetime import datetime, timedelta


def get_profit_summary(business_id: int, days: int = 7) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT COALESCE(SUM(revenue), 0) AS total_revenue,
               COALESCE(SUM(quantity_sold), 0) AS total_units_sold,
               COUNT(*) AS num_transactions
        FROM sales WHERE sale_date >= ? AND business_id = ?
    """, (since_date, business_id))
    sales_row = dict(cursor.fetchone())

    cursor.execute("""
        SELECT COALESCE(SUM(cost), 0) AS total_expenses,
               COUNT(*) AS num_restocks
        FROM restock_log WHERE restock_date >= ? AND business_id = ?
    """, (since_date, business_id))
    expense_row = dict(cursor.fetchone())

    revenue  = sales_row["total_revenue"]
    expenses = expense_row["total_expenses"]
    profit   = revenue - expenses
    margin   = round((profit / revenue * 100), 1) if revenue > 0 else 0
    conn.close()

    return {
        "period_days": days, "since_date": since_date,
        "total_revenue": round(revenue, 2),
        "total_expenses": round(expenses, 2),
        "gross_profit": round(profit, 2),
        "profit_margin_pct": margin,
        "total_units_sold": round(sales_row["total_units_sold"], 1),
        "num_transactions": sales_row["num_transactions"],
        "num_restocks": expense_row["num_restocks"],
    }


def get_product_margins(business_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, category, unit, unit_cost, selling_price,
               ROUND((selling_price - unit_cost), 2) AS profit_per_unit,
               CASE WHEN selling_price > 0
                    THEN ROUND((selling_price - unit_cost) / selling_price * 100, 1)
                    ELSE 0 END AS margin_pct
        FROM products WHERE business_id = ?
        ORDER BY margin_pct DESC
    """, (business_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_expense_breakdown(business_id: int, days: int = 30) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT p.name AS product, p.category,
               SUM(r.quantity_added) AS total_units_restocked,
               SUM(r.cost) AS total_spent,
               COUNT(r.id) AS num_restock_events,
               MAX(r.restock_date) AS last_restock_date
        FROM restock_log r JOIN products p ON p.id = r.product_id
        WHERE r.restock_date >= ? AND r.business_id = ?
        GROUP BY p.id ORDER BY total_spent DESC
    """, (since_date, business_id))

    rows = cursor.fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    total = sum(r["total_spent"] for r in result)
    for r in result:
        r["pct_of_total_expenses"] = round(r["total_spent"] / total * 100, 1) if total > 0 else 0
    return result


def get_cashflow(business_id: int, days: int = 14) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    dates = [
        (datetime.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days - 1, -1, -1)
    ]

    cursor.execute("""
        SELECT sale_date, COALESCE(SUM(revenue), 0) AS revenue
        FROM sales WHERE sale_date >= ? AND business_id = ?
        GROUP BY sale_date
    """, (dates[0], business_id))
    sales_by_date = {row["sale_date"]: row["revenue"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT restock_date, COALESCE(SUM(cost), 0) AS cost
        FROM restock_log WHERE restock_date >= ? AND business_id = ?
        GROUP BY restock_date
    """, (dates[0], business_id))
    costs_by_date = {row["restock_date"]: row["cost"] for row in cursor.fetchall()}
    conn.close()

    return [{
        "date": date,
        "revenue": round(sales_by_date.get(date, 0), 2),
        "expenses": round(costs_by_date.get(date, 0), 2),
        "net": round(sales_by_date.get(date, 0) - costs_by_date.get(date, 0), 2),
    } for date in dates]


def get_restock_budget(business_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, p.unit, p.current_stock,
               p.reorder_quantity, p.unit_cost,
               p.reorder_quantity * p.unit_cost AS restock_cost,
               s.name AS supplier_name, s.phone AS supplier_phone
        FROM products p
        LEFT JOIN suppliers s ON s.product_id = p.id
        WHERE p.current_stock <= p.reorder_threshold AND p.business_id = ?
        ORDER BY restock_cost DESC
    """, (business_id,))
    rows = cursor.fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    total_budget = sum(item["restock_cost"] for item in items)
    return {"total_budget_naira": round(total_budget, 2), "num_products": len(items), "items": items}


FINANCE_TOOLS = [
    {"name": "get_profit_summary", "description": "Calculates total revenue, expenses, gross profit and profit margin for the last N days.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "description": "Number of days to look back. Default 7."}}, "required": []}},
    {"name": "get_product_margins", "description": "Returns profit margin percentage for every product.", "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_expense_breakdown", "description": "Shows all restock spending grouped by product.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "description": "Number of days to look back. Default 30."}}, "required": []}},
    {"name": "get_cashflow", "description": "Returns day-by-day money in vs money out for the last N days.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "description": "Number of days to look back. Default 14."}}, "required": []}},
    {"name": "get_restock_budget", "description": "Calculates exactly how much cash is needed to restock all low-stock items.", "input_schema": {"type": "object", "properties": {}, "required": []}},
]


def run_finance_tool(tool_name: str, tool_input: dict, business_id: int = 1):
    if tool_name == "get_profit_summary":
        return get_profit_summary(business_id, **tool_input)
    elif tool_name == "get_product_margins":
        return get_product_margins(business_id)
    elif tool_name == "get_expense_breakdown":
        return get_expense_breakdown(business_id, **tool_input)
    elif tool_name == "get_cashflow":
        return get_cashflow(business_id, **tool_input)
    elif tool_name == "get_restock_budget":
        return get_restock_budget(business_id)
    else:
        return {"error": f"Unknown tool: {tool_name}"}