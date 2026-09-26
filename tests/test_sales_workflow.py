from datetime import date
from io import BytesIO

from openpyxl import Workbook

from sinana import create_app, db
from sinana.models import Customer, Order, Product, User, Visit


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'workflow.db'}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "ONE_C_API_TOKEN": "integration-secret",
    })


def seed(app):
    with app.app_context():
        manager = User(username="boss", full_name="Boss", role="manager")
        manager.set_password("password123")
        rep = User(username="rep", full_name="Rep", role="representative")
        rep.set_password("password123")
        db.session.add_all([manager, rep])
        db.session.flush()
        customer = Customer(name="Shop", address="Main st", assigned_rep_id=rep.id)
        db.session.add(customer)
        db.session.flush()
        db.session.add(Visit(visit_date=date.today(), sequence=1, customer_id=customer.id, representative_id=rep.id))
        db.session.commit()


def login(client, username):
    with client.session_transaction() as session:
        session["csrf_token"] = "token"
    response = client.post("/login", data={"username": username, "password": "password123", "csrf_token": "token"})
    assert response.status_code == 302


def test_excel_stock_and_order_exchange(tmp_path):
    app = make_app(tmp_path)
    seed(app)
    client = app.test_client()
    login(client, "boss")
    book = Workbook()
    sheet = book.active
    sheet.append(["Штрихкод", "Наименование", "Цена"])
    sheet.append(["460001", "Пирожное", 125])
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    response = client.post("/products", data={"csrf_token": "token", "file": (stream, "products.xlsx")}, content_type="multipart/form-data")
    assert response.status_code == 302
    response = client.post("/api/1c/stocks", json={"items": [{"barcode": "460001", "quantity": 19}]}, headers={"X-API-Key": "integration-secret"})
    assert response.json["updated"] == 1
    with app.app_context():
        product = Product.query.filter_by(barcode="460001").one()
        customer = Customer.query.one()
        rep = User.query.filter_by(username="rep").one()
        order = Order(number="SIN-TEST", customer_id=customer.id, representative_id=rep.id, total_amount=125)
        db.session.add(order)
        db.session.commit()
    response = client.get("/api/1c/orders", headers={"Authorization": "Bearer integration-secret"})
    assert response.json["items"][0]["number"] == "SIN-TEST"
    response = client.post("/api/1c/orders/ack", json={"orders": [{"number": "SIN-TEST", "external_id": "1c-guid", "external_number": "ЗК-15", "status": "confirmed"}]}, headers={"X-API-Key": "integration-secret"})
    assert response.json["updated"] == 1
    with app.app_context():
        order = Order.query.filter_by(number="SIN-TEST").one()
        assert order.external_number == "ЗК-15"
        assert order.status == "confirmed"


def test_first_visit_captures_customer_gps(tmp_path):
    app = make_app(tmp_path)
    seed(app)
    client = app.test_client()
    login(client, "rep")
    with app.app_context():
        visit_id = Visit.query.one().id
    response = client.post(f"/visits/{visit_id}/start", data={"csrf_token": "token", "latitude": "45.01", "longitude": "39.02"})
    assert response.status_code == 302
    with app.app_context():
        customer = Customer.query.one()
        assert customer.latitude == 45.01
        assert Visit.query.one().status == "in_progress"


def test_all_role_pages_render(tmp_path):
    app = make_app(tmp_path)
    seed(app)
    client = app.test_client()
    login(client, "boss")
    for path in ["/", "/orders", "/customers", "/routes", "/tracking", "/products", "/team", "/settings", "/mobile?rep_id=2"]:
        response = client.get(path)
        assert response.status_code == 200, path
