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
    debt = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    representative = db.relationship("User", foreign_keys=[assigned_rep_id])


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
    name = db.Column(db.String(300), nullable=False, index=True)
    price = db.Column(db.Numeric(14, 2), nullable=False, default=0)
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
