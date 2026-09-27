from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(160), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(24), nullable=False, default="representative", index=True)
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_latitude = db.Column(db.Float)
    last_longitude = db.Column(db.Float)
    last_location_at = db.Column(db.DateTime)

    @property
    def is_active(self):
        return self.is_active_user

    @property
    def is_manager(self):
        return self.role == "manager"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    gps_captured_at = db.Column(db.DateTime)
    assigned_rep_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    counterparty_id = db.Column(db.Integer, db.ForeignKey("counterparty.id"), index=True)
    debt = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    representative = db.relationship("User", foreign_keys=[assigned_rep_id])
    counterparty = db.relationship("Counterparty", foreign_keys=[counterparty_id])


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visit_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    sequence = db.Column(db.Integer, nullable=False, default=1)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    representative_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default="planned")
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    result = db.Column(db.String(24))
    start_latitude = db.Column(db.Float)
    start_longitude = db.Column(db.Float)
    customer = db.relationship("Customer")
    representative = db.relationship("User")


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    representative_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="submitted")
    external_id = db.Column(db.String(100), unique=True, index=True)
    external_number = db.Column(db.String(100))
    synced_at = db.Column(db.DateTime)
    sync_error = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    customer = db.relationship("Customer")
    representative = db.relationship("User")
    items = db.relationship("OrderItem", cascade="all, delete-orphan", back_populates="order")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(80), unique=True, nullable=False, index=True)
    external_id = db.Column(db.String(100), unique=True, index=True)
    external_group_id = db.Column(db.String(100), index=True)
    name = db.Column(db.String(300), nullable=False, index=True)
    product_type = db.Column(db.String(24), nullable=False, default="finished", index=True)
    unit = db.Column(db.String(20), nullable=False, default="шт")
    shelf_life_days = db.Column(db.Integer)
    allergens = db.Column(db.String(500))
    price = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    calculated_cost = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    stock_qty = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    price = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")


class LocationPing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    user = db.relationship("User")


class PhotoReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visit.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    visit = db.relationship("Visit", backref=db.backref("photos", cascade="all, delete-orphan"))


class Setting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(500), nullable=False, default="")


class SyncLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(24), nullable=False)
    items_count = db.Column(db.Integer, nullable=False, default=0)
    message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class Counterparty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(100), unique=True, index=True)
    name = db.Column(db.String(300), nullable=False, index=True)
    tax_id = db.Column(db.String(20), index=True)
    registration_code = db.Column(db.String(20))
    legal_address = db.Column(db.String(500))
    phone = db.Column(db.String(80))
    email = db.Column(db.String(160))
    price_type_id = db.Column(db.Integer, db.ForeignKey("price_type.id"), index=True)
    payment_terms_days = db.Column(db.Integer, nullable=False, default=0)
    debt = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    price_type = db.relationship("PriceType")


class ReceivableTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    counterparty_id = db.Column(db.Integer, db.ForeignKey("counterparty.id"), nullable=False, index=True)
    transaction_type = db.Column(db.String(24), nullable=False, index=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    note = db.Column(db.String(500))
    balance_after = db.Column(db.Numeric(14, 2), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    counterparty = db.relationship("Counterparty")
    created_by = db.relationship("User")


class Warehouse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(100), unique=True, index=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    warehouse_type = db.Column(db.String(30), nullable=False, default="finished")
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class StockBalance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouse.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    warehouse = db.relationship("Warehouse")
    product = db.relationship("Product")
    __table_args__ = (db.UniqueConstraint("warehouse_id", "product_id", name="uq_stock_warehouse_product"),)


class PriceType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(100), unique=True, index=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class ProductPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    price_type_id = db.Column(db.Integer, db.ForeignKey("price_type.id"), nullable=False, index=True)
    price = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    valid_from = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    product = db.relationship("Product")
    price_type = db.relationship("PriceType")
    __table_args__ = (db.UniqueConstraint("product_id", "price_type_id", name="uq_product_price_type"),)


class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, unique=True)
    output_quantity = db.Column(db.Numeric(14, 3), nullable=False, default=1)
    labor_cost = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    overhead_percent = db.Column(db.Numeric(8, 3), nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    product = db.relationship("Product")
    items = db.relationship("RecipeItem", cascade="all, delete-orphan", back_populates="recipe")


class RecipeItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipe.id"), nullable=False, index=True)
    component_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Numeric(14, 4), nullable=False)
    loss_percent = db.Column(db.Numeric(8, 3), nullable=False, default=0)
    recipe = db.relationship("Recipe", back_populates="items")
    component = db.relationship("Product")


class ProductionOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), nullable=False, unique=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    source_warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouse.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouse.id"), nullable=False)
    planned_quantity = db.Column(db.Numeric(14, 3), nullable=False)
    actual_quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="planned", index=True)
    planned_date = db.Column(db.Date, nullable=False, default=date.today)
    produced_at = db.Column(db.DateTime)
    batch_number = db.Column(db.String(80))
    expires_at = db.Column(db.Date)
    actual_cost = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    product = db.relationship("Product")
    source_warehouse = db.relationship("Warehouse", foreign_keys=[source_warehouse_id])
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])


class SalesReturn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), nullable=False, unique=True)
    external_id = db.Column(db.String(100), unique=True, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), index=True)
    counterparty_id = db.Column(db.Integer, db.ForeignKey("counterparty.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouse.id"), nullable=False)
    reason = db.Column(db.String(500))
    status = db.Column(db.String(24), nullable=False, default="draft")
    total_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    synced_at = db.Column(db.DateTime)
    order = db.relationship("Order")
    counterparty = db.relationship("Counterparty")
    warehouse = db.relationship("Warehouse")
    items = db.relationship("SalesReturnItem", cascade="all, delete-orphan", back_populates="sales_return")


class SalesReturnItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey("sales_return.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    price = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    sales_return = db.relationship("SalesReturn", back_populates="items")
    product = db.relationship("Product")
