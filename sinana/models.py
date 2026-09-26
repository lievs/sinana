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
    customer = db.relationship("Customer")
    representative = db.relationship("User")


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    representative_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="submitted")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    customer = db.relationship("Customer")
    representative = db.relationship("User")

