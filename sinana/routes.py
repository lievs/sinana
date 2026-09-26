from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from . import db
from .models import Customer, Order, User, Visit

auth = Blueprint("auth", __name__)
main = Blueprint("main", __name__)


def manager_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_manager:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard" if current_user.is_manager else "main.mobile"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        user = User.query.filter_by(username=username).first()
        if not user or not user.is_active_user or not user.check_password(request.form.get("password") or ""):
            flash("Неверный логин или пароль", "danger")
        else:
            login_user(user)
            session["user_session_version"] = user.session_version
            return redirect(url_for("main.dashboard" if user.is_manager else "main.mobile"))
    return render_template("login.html")


@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@main.route("/")
@login_required
def dashboard():
    if not current_user.is_manager:
        return redirect(url_for("main.mobile"))
    month_start = date.today().replace(day=1)
    start = datetime.combine(month_start, datetime.min.time())
    orders = Order.query.filter(Order.created_at >= start, Order.status != "cancelled").all()
    sales = sum(float(order.total_amount or 0) for order in orders)
    active_customers = Customer.query.filter_by(is_active=True).count()
    debt = db.session.query(func.coalesce(func.sum(Customer.debt), 0)).scalar()
    today_visits = Visit.query.filter_by(visit_date=date.today()).all()
    representatives = User.query.filter_by(role="representative", is_active_user=True).all()
    return render_template(
        "dashboard.html",
        sales=sales,
        orders=orders,
        active_customers=active_customers,
        debt=debt,
        today_visits=today_visits,
        representatives=representatives,
    )


@main.route("/mobile")
@login_required
def mobile():
    rep = current_user
    if current_user.is_manager and request.args.get("rep_id", type=int):
        rep = User.query.filter_by(id=request.args.get("rep_id", type=int), role="representative").first_or_404()
    visits = Visit.query.filter_by(visit_date=date.today(), representative_id=rep.id).order_by(Visit.sequence).all()
    day_start = datetime.combine(date.today(), datetime.min.time())
    orders = Order.query.filter(Order.representative_id == rep.id, Order.created_at >= day_start).all()
    return render_template("mobile.html", representative=rep, visits=visits, orders=orders)


@main.route("/team")
@manager_required
def team():
    users = User.query.order_by(User.role, User.full_name).all()
    return render_template("team.html", users=users)


@main.route("/team/create", methods=["POST"])
@manager_required
def team_create():
    username = (request.form.get("username") or "").strip()
    full_name = (request.form.get("full_name") or "").strip()
    password = request.form.get("password") or ""
    role = request.form.get("role") or "representative"
    if role not in ("manager", "representative"):
        abort(400)
    if not username or not full_name or len(password) < 8:
        flash("Заполните имя, логин и пароль не короче 8 символов", "danger")
    elif User.query.filter_by(username=username).first():
        flash("Такой логин уже существует", "danger")
    else:
        user = User(username=username, full_name=full_name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Сотрудник добавлен", "success")
    return redirect(url_for("main.team"))


@main.route("/team/<int:user_id>/password", methods=["POST"])
@manager_required
def team_password(user_id):
    user = db.get_or_404(User, user_id)
    password = request.form.get("password") or ""
    if len(password) < 8:
        flash("Пароль должен содержать не менее 8 символов", "danger")
    else:
        user.set_password(password)
        user.session_version += 1
        db.session.commit()
        flash("Пароль изменён, прежние сессии завершены", "success")
    return redirect(url_for("main.team"))


@main.route("/team/<int:user_id>/toggle", methods=["POST"])
@manager_required
def team_toggle(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("Нельзя отключить свою учётную запись", "danger")
    else:
        user.is_active_user = not user.is_active_user
        user.session_version += 1
        db.session.commit()
        flash("Статус сотрудника изменён", "success")
    return redirect(url_for("main.team"))

