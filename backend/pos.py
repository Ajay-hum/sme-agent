import sys
import os
sys.path.append(os.path.dirname(__file__))

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database.models import get_connection
from auth.utils import decode_token

router = APIRouter(prefix="/pos", tags=["pos"])


def get_business_id(authorization: Optional[str]) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return payload["business_id"]


# ── Request models ────────────────────────────────────────────────────────────
class CartItem(BaseModel):
    product_id: int
    quantity:   float


class POSSaleRequest(BaseModel):
    items:               list[CartItem]
    discount_naira:      Optional[float] = 0     # flat Naira amount off the total
    discount_percent:    Optional[float] = 0     # percentage off the total
    # Only one of the two should be used at a time; if both are sent,
    # discount_naira takes priority and discount_percent is recalculated to match.


# ── Process a full cart sale ──────────────────────────────────────────────────
@router.post("/sale")
def process_pos_sale(request: POSSaleRequest,
                     authorization: Optional[str] = Header(None)):
    """
    Processes a multi-item POS sale in one transaction.
    - Validates stock availability for every item before committing anything
    - Applies a discount (Naira or %) proportionally across line items
    - Deducts stock and records each sale with its share of the discount
    - Returns a full receipt
    """
    business_id = get_business_id(authorization)

    if not request.items:
        raise HTTPException(status_code=400, detail="Cart is empty.")

    conn = get_connection()
    cursor = conn.cursor()

    # ── Step 1: Look up every product and validate stock BEFORE writing anything ──
    line_items = []
    subtotal = 0.0

    for item in request.items:
        cursor.execute("""
            SELECT id, name, unit, current_stock, selling_price
            FROM products WHERE id = ? AND business_id = ?
        """, (item.product_id, business_id))
        product = cursor.fetchone()

        if not product:
            conn.close()
            raise HTTPException(
                status_code=404,
                detail=f"Product ID {item.product_id} not found in your store."
            )

        product = dict(product)

        if product["current_stock"] < item.quantity:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=(f"Not enough stock for {product['name']}. "
                        f"Requested {item.quantity}, only {product['current_stock']} available.")
            )

        line_total = round(item.quantity * product["selling_price"], 2)
        subtotal += line_total

        line_items.append({
            "product_id":    product["id"],
            "name":          product["name"],
            "unit":          product["unit"],
            "quantity":      item.quantity,
            "unit_price":    product["selling_price"],
            "line_total":    line_total,
            "current_stock": product["current_stock"],
        })

    # ── Step 2: Calculate the discount ──────────────────────────────────────────
    if request.discount_naira and request.discount_naira > 0:
        discount_amount = min(request.discount_naira, subtotal)  # can't discount more than the total
    elif request.discount_percent and request.discount_percent > 0:
        discount_amount = round(subtotal * (request.discount_percent / 100), 2)
    else:
        discount_amount = 0.0

    discount_pct_effective = round((discount_amount / subtotal * 100), 1) if subtotal > 0 else 0
    final_total = round(subtotal - discount_amount, 2)

    # ── Step 3: Commit everything — deduct stock, record each sale ──────────────
    today = datetime.today().strftime("%Y-%m-%d")
    receipt_items = []

    for line in line_items:
        # Discount is spread across items proportional to their share of the subtotal
        item_share = (line["line_total"] / subtotal) if subtotal > 0 else 0
        item_discount = round(discount_amount * item_share, 2)
        item_revenue  = round(line["line_total"] - item_discount, 2)

        new_stock = round(line["current_stock"] - line["quantity"], 2)

        cursor.execute(
            "UPDATE products SET current_stock = ? WHERE id = ?",
            (new_stock, line["product_id"])
        )

        cursor.execute("""
            INSERT INTO sales
                (product_id, quantity_sold, sale_date, revenue, discount, business_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (line["product_id"], line["quantity"], today,
              item_revenue, item_discount, business_id))

        receipt_items.append({
            "name":         line["name"],
            "unit":         line["unit"],
            "quantity":     line["quantity"],
            "unit_price":   line["unit_price"],
            "line_total":   line["line_total"],
            "discount":     item_discount,
            "final_amount": item_revenue,
        })

    conn.commit()
    conn.close()

    return {
        "success":               True,
        "date":                  today,
        "items":                 receipt_items,
        "subtotal":              round(subtotal, 2),
        "discount_amount":       discount_amount,
        "discount_pct_effective": discount_pct_effective,
        "total":                 final_total,
    }