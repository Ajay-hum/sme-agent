import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import get_connection
from datetime import datetime, timedelta


# ── Tool 1: Profit summary ────────────────────────────────────────────────────
def get_profit_summary(days: int = 7) -> dict:
    """
    Calculates total revenue, total restock costs, and gross profit
    for the last N days.
    """
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Total revenue from sales
    cursor.execute("""
        SELECT COALESCE(SUM(revenue), 0) AS total_revenue,
               COALESCE(SUM(quantity_sold), 0) AS total_units_sold,
               COUNT(*) AS num_transactions
        FROM sales
        WHERE sale_date >= ?
    """, (since_date,))
    sales_row = dict(cursor.fetchone())

    # Total restock costs (expenses)
    cursor.execute("""
        SELECT COALESCE(SUM(cost), 0) AS total_expenses,
               COUNT(*) AS num_restocks
        FROM restock_log
        WHERE restock_date >= ?
    """, (since_date,))
    expense_row = dict(cursor.fetchone())

    revenue  = sales_row["total_revenue"]
    expenses = expense_row["total_expenses"]
    profit   = revenue - expenses
    margin   = round((profit / revenue * 100), 1) if revenue > 0 else 0

    conn.close()
    return {
        "period_days":       days,
        "since_date":        since_date,
        "total_revenue":     round(revenue, 2),
        "total_expenses":    round(expenses, 2),
        "gross_profit":      round(profit, 2),
        "profit_margin_pct": margin,
        "total_units_sold":  round(sales_row["total_units_sold"], 1),
        "num_transactions":  sales_row["num_transactions"],
        "num_restocks":      expense_row["num_restocks"],
    }


# ── Tool 2: Product margins ───────────────────────────────────────────────────
def get_product_margins() -> list[dict]:
    """
    Returns margin percentage and profit per unit for every product.
    Sorted from highest to lowest margin.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            name,
            category,
            unit,
            unit_cost,
            selling_price,
            ROUND((selling_price - unit_cost), 2) AS profit_per_unit,
            CASE
                WHEN selling_price > 0
                THEN ROUND((selling_price - unit_cost) / selling_price * 100, 1)
                ELSE 0
            END AS margin_pct
        FROM products
        ORDER BY margin_pct DESC
    """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Tool 3: Expense breakdown ─────────────────────────────────────────────────
def get_expense_breakdown(days: int = 30) -> list[dict]:
    """
    Lists all restock costs for the last N days grouped by product.
    Shows where money is going out.
    """
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT
            p.name AS product,
            p.category,
            SUM(r.quantity_added) AS total_units_restocked,
            SUM(r.cost)           AS total_spent,
            COUNT(r.id)           AS num_restock_events,
            MAX(r.restock_date)   AS last_restock_date
        FROM restock_log r
        JOIN products p ON p.id = r.product_id
        WHERE r.restock_date >= ?
        GROUP BY p.id
        ORDER BY total_spent DESC
    """, (since_date,))

    rows = cursor.fetchall()
    conn.close()

    result = [dict(r) for r in rows]

    # Add total for context
    total = sum(r["total_spent"] for r in result)
    for r in result:
        r["pct_of_total_expenses"] = round(
            r["total_spent"] / total * 100, 1
        ) if total > 0 else 0

    return result


# ── Tool 4: Cash flow by day ──────────────────────────────────────────────────
def get_cashflow(days: int = 14) -> list[dict]:
    """
    Returns day-by-day cash flow: money in (sales revenue) vs
    money out (restock costs) for the last N days.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Build a list of the last N dates
    dates = [
        (datetime.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days - 1, -1, -1)
    ]

    # Daily sales revenue
    cursor.execute("""
        SELECT sale_date, COALESCE(SUM(revenue), 0) AS revenue
        FROM sales
        WHERE sale_date >= ?
        GROUP BY sale_date
    """, (dates[0],))
    sales_by_date = {row["sale_date"]: row["revenue"] for row in cursor.fetchall()}

    # Daily restock costs
    cursor.execute("""
        SELECT restock_date, COALESCE(SUM(cost), 0) AS cost
        FROM restock_log
        WHERE restock_date >= ?
        GROUP BY restock_date
    """, (dates[0],))
    costs_by_date = {row["restock_date"]: row["cost"] for row in cursor.fetchall()}

    conn.close()

    cashflow = []
    for date in dates:
        revenue  = sales_by_date.get(date, 0)
        expenses = costs_by_date.get(date, 0)
        cashflow.append({
            "date":       date,
            "revenue":    round(revenue, 2),
            "expenses":   round(expenses, 2),
            "net":        round(revenue - expenses, 2),
        })

    return cashflow


# ── Tool 5: Restock budget ────────────────────────────────────────────────────
def get_restock_budget() -> dict:
    """
    Calculates exactly how much cash the owner needs right now
    to restock all low-stock products to their reorder quantities.
    Broken down by product and supplier.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            p.name,
            p.unit,
            p.current_stock,
            p.reorder_quantity,
            p.unit_cost,
            p.reorder_quantity * p.unit_cost AS restock_cost,
            s.name  AS supplier_name,
            s.phone AS supplier_phone
        FROM products p
        LEFT JOIN suppliers s ON s.product_id = p.id
        WHERE p.current_stock <= p.reorder_threshold
        ORDER BY restock_cost DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    items = [dict(r) for r in rows]
    total_budget = sum(item["restock_cost"] for item in items)

    return {
        "total_budget_naira": round(total_budget, 2),
        "num_products":       len(items),
        "items":              items,
    }


# ── Tool registry ─────────────────────────────────────────────────────────────
FINANCE_TOOLS = [
    {
        "name": "get_profit_summary",
        "description": (
            "Calculates total revenue, expenses, gross profit and profit margin "
            "for the last N days. Use when owner asks about profit, earnings, "
            "or how the business is doing financially."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default 7.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_product_margins",
        "description": (
            "Returns profit margin percentage for every product. "
            "Use when owner asks which products make the most profit, "
            "or wants to know margins."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_expense_breakdown",
        "description": (
            "Shows all restock spending grouped by product. "
            "Use when owner asks where money is going, "
            "or what the biggest expenses are."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default 30.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_cashflow",
        "description": (
            "Returns day-by-day money in vs money out for the last N days. "
            "Use when owner asks about cash flow, slow days, "
            "or daily financial patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default 14.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_restock_budget",
        "description": (
            "Calculates exactly how much cash is needed right now to restock "
            "all low-stock items. Use when owner asks how much money they need "
            "for restocking or wants a shopping budget."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ── Tool dispatcher ───────────────────────────────────────────────────────────
def run_finance_tool(tool_name: str, tool_input: dict):
    if tool_name == "get_profit_summary":
        return get_profit_summary(**tool_input)
    elif tool_name == "get_product_margins":
        return get_product_margins()
    elif tool_name == "get_expense_breakdown":
        return get_expense_breakdown(**tool_input)
    elif tool_name == "get_cashflow":
        return get_cashflow(**tool_input)
    elif tool_name == "get_restock_budget":
        return get_restock_budget()
    else:
        return {"error": f"Unknown tool: {tool_name}"}