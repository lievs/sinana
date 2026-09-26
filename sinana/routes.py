import math
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from openpyxl import load_workbook
from sqlalchemy import func
from werkzeug.utils import secure_filename

from . import db
from .models import Customer, LocationPing, Order, OrderItem, PhotoReport, Product, Setting, SyncLog, User, Visit

auth = Blueprint("auth", __name__)
main = Blueprint("main", __name__)
api = Blueprint("api", __name__)
PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic"}
ORDER_STATUSES = {"submitted", "confirmed", "assembled", "delivered", "paid", "cancelled"}


def manager_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_manager:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def one_c_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        configured = current_app.config.get("ONE_C_API_TOKEN") or ""
        supplied = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not configured:
            return jsonify(error="Интеграция с 1С не настроена"), 503
        if not supplied or supplied != configured:
            return jsonify(error="Недействительный ключ"), 401
        return view(*args, **kwargs)

    return wrapped


def setting(key, default=""):
    row = db.session.get(Setting, key)
    return row.value if row else default


def bool_setting(key, default=False):
    return setting(key, "1" if default else "0") == "1"


def decimal_value(value, default=Decimal("0")):
    try:
        return Decimal(str(value or "0").replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return default


def barcode_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_coordinate(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def can_manage_visit(visit):
    return current_user.is_manager or visit.representative_id == current_user.id


@main.route("/sw.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


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
    session.clear()
    return redirect(url_for("auth.login"))


@main.route("/")
@login_required
def dashboard():
    if not current_user.is_manager:
        return redirect(url_for("main.mobile"))
    start = datetime.combine(date.today().replace(day=1), datetime.min.time())
    orders = Order.query.filter(Order.created_at >= start, Order.status != "cancelled").all()
    sales = sum(float(order.total_amount or 0) for order in orders)
    monthly_plan = float(setting("monthly_sales_plan", "1000000") or 1000000)
    plan_percent = round(min(sales / monthly_plan * 100, 999), 1) if monthly_plan else 0
    today = date.today()
    chart_values = []
    for offset in range(4, -1, -1):
        period_end = datetime.combine(today, datetime.max.time())
        period_start = period_end.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=offset * 7 + 6)
        period_finish = period_start + timedelta(days=7)
        chart_values.append(sum(float(order.total_amount or 0) for order in orders if period_start <= order.created_at < period_finish))
    chart_max = max(chart_values + [monthly_plan / 4 if monthly_plan else 1, 1])
    chart_points = " ".join(f"{40 + index * 155},{190 - value / chart_max * 145:.1f}" for index, value in enumerate(chart_values))
    return render_template(
        "dashboard.html",
        sales=sales,
        orders=orders,
        active_customers=Customer.query.filter_by(is_active=True).count(),
        debt=db.session.query(func.coalesce(func.sum(Customer.debt), 0)).scalar(),
        today_visits=Visit.query.filter_by(visit_date=date.today()).all(),
        representatives=User.query.filter_by(role="representative", is_active_user=True).all(),
        unsynced_orders=Order.query.filter(Order.synced_at.is_(None), Order.status != "cancelled").count(),
        monthly_plan=monthly_plan,
        plan_percent=plan_percent,
        chart_values=chart_values,
        chart_points=chart_points,
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
    return render_template("mobile.html", representative=rep, visits=visits, orders=orders, photo_required=bool_setting("photo_required", True), is_own_route=rep.id == current_user.id)


@main.route("/gps/ping", methods=["POST"])
@login_required
def gps_ping():
    payload = request.get_json(silent=True) or request.form
    latitude = parse_coordinate(payload.get("latitude"))
    longitude = parse_coordinate(payload.get("longitude"))
    accuracy = parse_coordinate(payload.get("accuracy"))
    if latitude is None or longitude is None or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return jsonify(error="Некорректные координаты"), 400
    now = datetime.utcnow()
    current_user.last_latitude, current_user.last_longitude, current_user.last_location_at = latitude, longitude, now
    db.session.add(LocationPing(user_id=current_user.id, latitude=latitude, longitude=longitude, accuracy=accuracy, recorded_at=now))
    db.session.commit()
    return jsonify(ok=True, recorded_at=now.isoformat())


@main.route("/visits/<int:visit_id>/start", methods=["POST"])
@login_required
def visit_start(visit_id):
    visit = db.get_or_404(Visit, visit_id)
    if not can_manage_visit(visit):
        abort(403)
    latitude, longitude = parse_coordinate(request.form.get("latitude")), parse_coordinate(request.form.get("longitude"))
    if latitude is None or longitude is None:
        flash("Для первого визита разрешите определение геопозиции", "danger")
        return redirect(url_for("main.mobile"))
    visit.status, visit.started_at = "in_progress", visit.started_at or datetime.utcnow()
    visit.start_latitude, visit.start_longitude = latitude, longitude
    if visit.customer.latitude is None or visit.customer.longitude is None:
        visit.customer.latitude, visit.customer.longitude = latitude, longitude
        visit.customer.gps_captured_at = datetime.utcnow()
        flash("GPS-точка клиента сохранена для следующих маршрутов", "success")
    db.session.commit()
    return redirect(url_for("main.mobile"))


@main.route("/visits/<int:visit_id>/complete", methods=["POST"])
@login_required
def visit_complete(visit_id):
    visit = db.get_or_404(Visit, visit_id)
    if not can_manage_visit(visit):
        abort(403)
    uploaded = request.files.get("photo")
    if bool_setting("photo_required", True) and not uploaded and not visit.photos:
        flash("Для завершения визита требуется фотография выкладки", "danger")
        return redirect(url_for("main.mobile"))
    if uploaded and uploaded.filename:
        ext = uploaded.filename.rsplit(".", 1)[-1].lower() if "." in uploaded.filename else ""
        if ext not in PHOTO_EXTENSIONS:
            flash("Разрешены фотографии JPG, PNG, WEBP или HEIC", "danger")
            return redirect(url_for("main.mobile"))
        stored_name = f"{visit.id}-{uuid4().hex}.{ext}"
        uploaded.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name))
        db.session.add(PhotoReport(visit_id=visit.id, filename=stored_name, original_name=secure_filename(uploaded.filename)))
    visit.status, visit.completed_at = "completed", datetime.utcnow()
    visit.result = request.form.get("result") if request.form.get("result") in {"order", "no_order", "visited"} else "visited"
    db.session.commit()
    flash("Визит завершён", "success")
    return redirect(url_for("main.mobile"))


@main.route("/route/finish", methods=["POST"])
@login_required
def route_finish():
    visits = Visit.query.filter_by(visit_date=date.today(), representative_id=current_user.id).all()
    incomplete = [visit for visit in visits if visit.status != "completed"]
    missing_photos = [visit for visit in visits if not visit.photos] if bool_setting("photo_required", True) else []
    if incomplete:
        flash(f"Сначала завершите все точки: осталось {len(incomplete)}", "danger")
    elif missing_photos:
        flash(f"Не хватает фотографий по {len(missing_photos)} точкам", "danger")
    else:
        flash("Маршрут завершён, данные и фотоматериалы сохранены", "success")
    return redirect(url_for("main.mobile"))


@main.route("/photos/<path:filename>")
@login_required
def photo(filename):
    report = PhotoReport.query.filter_by(filename=filename).first_or_404()
    if not current_user.is_manager and report.visit.representative_id != current_user.id:
        abort(403)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@main.route("/orders/new/<int:customer_id>", methods=["GET", "POST"])
@login_required
def order_new(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    if not current_user.is_manager and customer.assigned_rep_id != current_user.id:
        abort(403)
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    if request.method == "POST":
        selected, total = [], Decimal("0")
        for product in products:
            qty = decimal_value(request.form.get(f"qty_{product.id}"))
            if qty > 0:
                selected.append((product, qty))
                total += qty * product.price
        if not selected:
            flash("Добавьте хотя бы один товар", "danger")
        else:
            number = f"SIN-{datetime.now():%Y%m%d}-{uuid4().hex[:6].upper()}"
            order = Order(number=number, customer_id=customer.id, representative_id=current_user.id, total_amount=total)
            db.session.add(order)
            db.session.flush()
            for product, qty in selected:
                db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=qty, price=product.price))
            visit = Visit.query.filter_by(customer_id=customer.id, representative_id=current_user.id, visit_date=date.today()).first()
            if visit:
                visit.result = "order"
            db.session.commit()
            flash(f"Заказ {number} создан и ожидает передачи в 1С", "success")
            return redirect(url_for("main.mobile"))
    return render_template("order_form.html", customer=customer, products=products)


@main.route("/orders")
@manager_required
def orders():
    return render_template("orders.html", orders=Order.query.order_by(Order.created_at.desc()).limit(300).all())


@main.route("/team")
@manager_required
def team():
    return render_template("team.html", users=User.query.order_by(User.role, User.full_name).all())


@main.route("/team/create", methods=["POST"])
@manager_required
def team_create():
    username = (request.form.get("username") or "").strip()
    full_name, password = (request.form.get("full_name") or "").strip(), request.form.get("password") or ""
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
    user, password = db.get_or_404(User, user_id), request.form.get("password") or ""
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


@main.route("/team/<int:user_id>/delete", methods=["POST"])
@manager_required
def team_delete(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("Нельзя удалить свою учётную запись", "danger")
    elif Customer.query.filter_by(assigned_rep_id=user.id).first() or Order.query.filter_by(representative_id=user.id).first():
        user.is_active_user = False
        user.session_version += 1
        db.session.commit()
        flash("Сотрудник отключён; история сохранена", "success")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Сотрудник удалён", "success")
    return redirect(url_for("main.team"))


@main.route("/team/<int:user_id>/role", methods=["POST"])
@manager_required
def team_role(user_id):
    user = db.get_or_404(User, user_id)
    role = request.form.get("role")
    if role not in {"manager", "representative"}:
        abort(400)
    if user.id == current_user.id and role != "manager":
        flash("Нельзя снять роль руководителя у своей учётной записи", "danger")
    else:
        user.role = role
        user.session_version += 1
        db.session.commit()
        flash("Роль изменена; сотрудник войдёт заново", "success")
    return redirect(url_for("main.team"))


@main.route("/customers", methods=["GET", "POST"])
@manager_required
def customers():
    reps = User.query.filter_by(role="representative", is_active_user=True).order_by(User.full_name).all()
    if request.method == "POST":
        name, address = (request.form.get("name") or "").strip(), (request.form.get("address") or "").strip()
        rep = db.session.get(User, request.form.get("representative_id", type=int))
        if not name or not address or not rep or rep.role != "representative":
            flash("Заполните название, адрес и представителя", "danger")
        else:
            db.session.add(Customer(name=name, address=address, assigned_rep_id=rep.id))
            db.session.commit()
            flash("Торговая точка добавлена", "success")
        return redirect(url_for("main.customers"))
    return render_template("customers.html", customers=Customer.query.order_by(Customer.name).all(), representatives=reps)


@main.route("/customers/<int:customer_id>/toggle", methods=["POST"])
@manager_required
def customer_toggle(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    customer.is_active = not customer.is_active
    db.session.commit()
    return redirect(url_for("main.customers"))


@main.route("/routes", methods=["GET", "POST"])
@manager_required
def routes():
    reps = User.query.filter_by(role="representative", is_active_user=True).order_by(User.full_name).all()
    if request.method == "POST":
        rep_id, customer_ids = request.form.get("representative_id", type=int), request.form.getlist("customer_ids", type=int)
        try:
            visit_date = datetime.strptime(request.form.get("visit_date") or "", "%Y-%m-%d").date()
        except ValueError:
            visit_date = None
        rep = db.session.get(User, rep_id)
        if not rep or rep.role != "representative" or not visit_date or not customer_ids:
            flash("Выберите сотрудника, дату и торговые точки", "danger")
        else:
            existing = {row.customer_id for row in Visit.query.filter_by(representative_id=rep.id, visit_date=visit_date).all()}
            sequence = len(existing)
            for customer_id in customer_ids:
                customer = db.session.get(Customer, customer_id)
                if customer and customer.id not in existing:
                    sequence += 1
                    db.session.add(Visit(visit_date=visit_date, sequence=sequence, customer_id=customer.id, representative_id=rep.id))
            db.session.commit()
            flash("Маршрут сохранён", "success")
        return redirect(url_for("main.routes", date=(visit_date or date.today()).isoformat()))
    try:
        route_date = datetime.strptime(request.args.get("date") or date.today().isoformat(), "%Y-%m-%d").date()
    except ValueError:
        route_date = date.today()
    visits = Visit.query.filter_by(visit_date=route_date).order_by(Visit.representative_id, Visit.sequence).all()
    return render_template("routes.html", representatives=reps, customers=Customer.query.filter_by(is_active=True).order_by(Customer.name).all(), visits=visits, route_date=route_date)


@main.route("/routes/<int:user_id>/optimize", methods=["POST"])
@manager_required
def route_optimize(user_id):
    try:
        visit_date = datetime.strptime(request.form.get("visit_date") or "", "%Y-%m-%d").date()
    except ValueError:
        abort(400)
    visits = Visit.query.filter_by(visit_date=visit_date, representative_id=user_id).all()
    located = [v for v in visits if v.customer.latitude is not None and v.customer.longitude is not None]
    missing = [v for v in visits if v not in located]
    user = db.get_or_404(User, user_id)
    current = (user.last_latitude, user.last_longitude) if user.last_latitude is not None else None
    ordered = []
    while located:
        chosen = located[0] if current is None else min(located, key=lambda v: (v.customer.latitude - current[0]) ** 2 + (v.customer.longitude - current[1]) ** 2)
        ordered.append(chosen)
        located.remove(chosen)
        current = (chosen.customer.latitude, chosen.customer.longitude)
    for sequence, visit in enumerate(ordered + sorted(missing, key=lambda v: v.sequence), 1):
        visit.sequence = sequence
    db.session.commit()
    flash("Маршрут перестроен по GPS-точкам", "success")
    return redirect(url_for("main.routes", date=visit_date.isoformat()))


@main.route("/tracking")
@manager_required
def tracking():
    return render_template("tracking.html", representatives=User.query.filter_by(role="representative", is_active_user=True).order_by(User.full_name).all())


@main.route("/products", methods=["GET", "POST"])
@manager_required
def products():
    if request.method == "POST":
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename.lower().endswith(".xlsx"):
            flash("Выберите файл Excel в формате .xlsx", "danger")
        else:
            workbook = load_workbook(uploaded, read_only=True, data_only=True)
            sheet = workbook.active
            headers = {str(cell.value or "").strip().lower(): i for i, cell in enumerate(next(sheet.iter_rows()))}
            barcode_col = next((headers[key] for key in headers if key in {"штрихкод", "barcode", "штрих-код"}), None)
            name_col = next((headers[key] for key in headers if key in {"наименование", "название", "name"}), None)
            price_col = next((headers[key] for key in headers if key in {"цена", "price"}), None)
            if barcode_col is None or name_col is None:
                flash("Нужны колонки «Штрихкод» и «Наименование»", "danger")
            else:
                count = 0
                for row in sheet.iter_rows(values_only=True):
                    barcode, name = barcode_value(row[barcode_col]), str(row[name_col] or "").strip()
                    if not barcode or not name:
                        continue
                    product = Product.query.filter_by(barcode=barcode).first() or Product(barcode=barcode)
                    product.name, product.is_active = name, True
                    if price_col is not None:
                        product.price = decimal_value(row[price_col])
                    db.session.add(product)
                    count += 1
                db.session.commit()
                flash(f"Загружено или обновлено позиций: {count}", "success")
        return redirect(url_for("main.products"))
    return render_template("products.html", products=Product.query.order_by(Product.name).limit(1000).all(), last_sync=SyncLog.query.order_by(SyncLog.created_at.desc()).first())


@main.route("/settings", methods=["GET", "POST"])
@manager_required
def settings():
    if request.method == "POST":
        values = {
            "photo_required": "1" if request.form.get("photo_required") else "0",
            "monthly_sales_plan": str(max(decimal_value(request.form.get("monthly_sales_plan")), 0)),
        }
        for key, value in values.items():
            row = db.session.get(Setting, key) or Setting(key=key)
            row.value = value
            db.session.add(row)
        db.session.commit()
        flash("Настройки сохранены", "success")
        return redirect(url_for("main.settings"))
    return render_template("settings.html", photo_required=bool_setting("photo_required", True), monthly_sales_plan=setting("monthly_sales_plan", "1000000"), api_configured=bool(current_app.config.get("ONE_C_API_TOKEN")))


def order_payload(order):
    return {"number": order.number, "external_id": order.external_id, "status": order.status, "created_at": order.created_at.isoformat(), "customer": {"id": order.customer.id, "name": order.customer.name, "address": order.customer.address}, "representative": {"id": order.representative.id, "name": order.representative.full_name}, "total_amount": float(order.total_amount), "items": [{"barcode": item.product.barcode, "name": item.product.name, "quantity": float(item.quantity), "price": float(item.price)} for item in order.items]}


@api.route("/health")
@one_c_required
def api_health():
    return jsonify(ok=True, service="sinana")


@api.route("/products")
@one_c_required
def api_products():
    return jsonify(items=[{"barcode": p.barcode, "name": p.name, "price": float(p.price), "stock": float(p.stock_qty)} for p in Product.query.filter_by(is_active=True).all()])


@api.route("/stocks", methods=["POST"])
@one_c_required
def api_stocks():
    items = (request.get_json(silent=True) or {}).get("items")
    if not isinstance(items, list):
        return jsonify(error="Ожидается массив items"), 400
    updated, unknown = 0, []
    for item in items:
        barcode = str(item.get("barcode") or "").strip()
        product = Product.query.filter_by(barcode=barcode).first()
        if not product:
            unknown.append(barcode)
            continue
        product.stock_qty = decimal_value(item.get("quantity"))
        if item.get("price") is not None:
            product.price = decimal_value(item.get("price"))
        updated += 1
    db.session.add(SyncLog(source="1c_stock", status="success", items_count=updated, message=f"Не найдено: {len(unknown)}"))
    db.session.commit()
    return jsonify(ok=True, updated=updated, unknown_barcodes=unknown)


@api.route("/orders")
@one_c_required
def api_orders():
    query = Order.query.filter(Order.status != "cancelled")
    if request.args.get("unsynced", "1") != "0":
        query = query.filter(Order.synced_at.is_(None))
    return jsonify(items=[order_payload(order) for order in query.order_by(Order.created_at).limit(500).all()])


@api.route("/orders/ack", methods=["POST"])
@one_c_required
def api_orders_ack():
    rows = (request.get_json(silent=True) or {}).get("orders")
    if not isinstance(rows, list):
        return jsonify(error="Ожидается массив orders"), 400
    updated, missing = 0, []
    for row in rows:
        number = str(row.get("number") or "").strip()
        order = Order.query.filter_by(number=number).first()
        if not order:
            missing.append(number)
            continue
        external_id = str(row.get("external_id") or "").strip() or None
        if external_id and Order.query.filter(Order.external_id == external_id, Order.id != order.id).first():
            continue
        order.external_id = external_id or order.external_id
        order.external_number = str(row.get("external_number") or "").strip() or order.external_number
        status = str(row.get("status") or "").strip()
        if status in ORDER_STATUSES:
            order.status = status
        order.synced_at, order.sync_error = datetime.utcnow(), None
        updated += 1
    db.session.add(SyncLog(source="1c_orders", status="success", items_count=updated, message=f"Не найдено: {len(missing)}"))
    db.session.commit()
    return jsonify(ok=True, updated=updated, missing=missing)


@api.route("/orders/statuses", methods=["POST"])
@one_c_required
def api_order_statuses():
    return api_orders_ack()
