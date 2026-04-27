from pydantic import BaseModel
from typing import Optional


# ── Product schemas ───────────────────────────────────────────────────────────
class ProductBase(BaseModel):
    name: str
    category: Optional[str] = None
    unit: Optional[str] = None
    current_stock: float = 0
    reorder_threshold: float = 10
    reorder_quantity: float = 50
    unit_cost: float = 0
    selling_price: float = 0


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    current_stock: Optional[float] = None
    reorder_threshold: Optional[float] = None
    reorder_quantity: Optional[float] = None
    unit_cost: Optional[float] = None
    selling_price: Optional[float] = None


class Product(ProductBase):
    id: int

    class Config:
        from_attributes = True


# ── Sale schemas ──────────────────────────────────────────────────────────────
class SaleCreate(BaseModel):
    product_id: int
    quantity_sold: float
    sale_date: str
    revenue: Optional[float] = None


class Sale(SaleCreate):
    id: int

    class Config:
        from_attributes = True


# ── Supplier schemas ──────────────────────────────────────────────────────────
class SupplierBase(BaseModel):
    name: str
    phone: Optional[str] = None
    product_id: Optional[int] = None
    lead_time_days: int = 1


class SupplierCreate(SupplierBase):
    pass


class Supplier(SupplierBase):
    id: int

    class Config:
        from_attributes = True


# ── Restock schemas ───────────────────────────────────────────────────────────
class RestockCreate(BaseModel):
    product_id: int
    quantity_added: float
    restock_date: str
    cost: Optional[float] = None
    supplier_id: Optional[int] = None


class Restock(RestockCreate):
    id: int

    class Config:
        from_attributes = True


# ── Chat schemas (API) ────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


class ChatResponse(BaseModel):
    response: str
    session_id: str


# ── Low stock alert schema ────────────────────────────────────────────────────
class LowStockAlert(BaseModel):
    name: str
    category: Optional[str]
    unit: Optional[str]
    current_stock: float
    reorder_threshold: float
    reorder_quantity: float
    unit_cost: float
    supplier_name: Optional[str]
    supplier_phone: Optional[str]
    lead_time_days: Optional[int]


# ── Reorder suggestion schema ─────────────────────────────────────────────────
class ReorderSuggestion(BaseModel):
    product: str
    unit: Optional[str]
    current_stock: float
    days_left: object        # float or "unknown"
    avg_daily_sales: float
    suggested_order_qty: float
    estimated_cost_naira: float
    supplier: Optional[str]
    supplier_phone: Optional[str]
    lead_time_days: Optional[int]