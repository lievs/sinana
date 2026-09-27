from datetime import date
from io import BytesIO

from openpyxl import Workbook

from sinana import create_app, db
from sinana.models import Counterparty, Customer, Order, OrderItem, PriceType, Product, ProductPrice, ProductionOrder, ReceivableTransaction, Recipe, RecipeItem, SalesReturn, Setting, StockBalance, User, Visit, Warehouse


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
    for path in ["/", "/orders", "/customers", "/routes", "/tracking", "/products", "/team", "/settings", "/mobile?rep_id=2", "/erp", "/counterparties", "/warehouses", "/price-types", "/recipes", "/production", "/returns"]:
        response = client.get(path)
        assert response.status_code == 200, path


def test_1c_catalog_uses_configured_group_and_syncs_directories(tmp_path):
    app = make_app(tmp_path)
    seed(app)
    client = app.test_client()
    with app.app_context():
        db.session.add(Setting(key="one_c_product_group_id", value="GROUP-CAKE"))
        db.session.commit()
    rejected = client.post("/api/1c/catalog", json={"group_id": "OTHER", "items": []}, headers={"X-API-Key": "integration-secret"})
    assert rejected.status_code == 400
    response = client.post("/api/1c/catalog", json={"group_id": "GROUP-CAKE", "full_sync": True, "items": [{"external_id": "P-1", "barcode": "460777", "name": "Торт", "type": "finished", "unit": "шт", "shelf_life_days": 5, "price": 900}]}, headers={"X-API-Key": "integration-secret"})
    assert response.json["updated"] == 1
    response = client.post("/api/1c/counterparties", json={"items": [{"external_id": "C-1", "name": "Магазин", "tax_id": "123", "debt": 100}]}, headers={"X-API-Key": "integration-secret"})
    assert response.json["updated"] == 1
    response = client.post("/api/1c/prices", json={"price_types": [{"external_id": "PT-1", "name": "Оптовая"}], "prices": [{"product_external_id": "P-1", "price_type_external_id": "PT-1", "price": 750}]}, headers={"X-API-Key": "integration-secret"})
    assert response.json["updated"] == 1
    response = client.post("/api/1c/warehouses", json={"items": [{"external_id": "W-1", "name": "Готовая продукция", "type": "finished"}]}, headers={"X-API-Key": "integration-secret"})
    assert response.json["updated"] == 1
    response = client.post("/api/1c/stocks", json={"items": [{"barcode": "460777", "warehouse_external_id": "W-1", "quantity": 12}]}, headers={"X-API-Key": "integration-secret"})
    assert response.json["updated"] == 1
    with app.app_context():
        assert Product.query.filter_by(external_group_id="GROUP-CAKE").one().stock_qty == 12
        assert Counterparty.query.filter_by(external_id="C-1").one().name == "Магазин"
        assert Warehouse.query.filter_by(external_id="W-1").one().name == "Готовая продукция"


def test_production_uses_recipe_cost_and_moves_stock(tmp_path):
    app = make_app(tmp_path)
    seed(app)
    client = app.test_client()
    login(client, "boss")
    with app.app_context():
        raw = Product(barcode="RAW", name="Мука", product_type="raw", unit="кг", calculated_cost=10)
        cake = Product(barcode="CAKE", name="Торт", product_type="finished", unit="шт")
        source = Warehouse(name="Сырьё", warehouse_type="raw")
        target = Warehouse(name="Готовая продукция", warehouse_type="finished")
        db.session.add_all([raw, cake, source, target])
        db.session.flush()
        recipe = Recipe(product_id=cake.id, output_quantity=10, labor_cost=20, overhead_percent=10)
        db.session.add(recipe)
        db.session.flush()
        db.session.add(RecipeItem(recipe_id=recipe.id, component_id=raw.id, quantity=5, loss_percent=0))
        db.session.add(StockBalance(warehouse_id=source.id, product_id=raw.id, quantity=100))
        production = ProductionOrder(number="PRD-TEST", product_id=cake.id, source_warehouse_id=source.id, warehouse_id=target.id, planned_quantity=10)
        db.session.add(production)
        db.session.commit()
        production_id = production.id
    response = client.post(f"/production/{production_id}/complete", data={"csrf_token": "token", "actual_quantity": "10", "batch_number": "B-1"})
    assert response.status_code == 302
    with app.app_context():
        production = db.session.get(ProductionOrder, production_id)
        assert production.status == "completed"
        assert float(production.actual_cost) == 7.7
        assert float(StockBalance.query.join(Product).filter(Product.barcode == "RAW").one().quantity) == 95
        assert float(StockBalance.query.join(Product).filter(Product.barcode == "CAKE").one().quantity) == 10


def test_manual_product_and_counterparty_receivables(tmp_path):
    app = make_app(tmp_path)
    seed(app)
    client = app.test_client()
    login(client, "boss")
    response = client.post("/products", data={
        "csrf_token": "token",
        "action": "manual",
        "barcode": "460999",
        "name": "Торт вручную",
        "unit": "шт",
        "product_type": "finished",
        "price": "1500",
        "calculated_cost": "700",
        "shelf_life_days": "5",
    })
    assert response.status_code == 302
    with app.app_context():
        price_type = PriceType(name="Оптовая")
        db.session.add(price_type)
        db.session.commit()
        price_type_id = price_type.id
        assert Product.query.filter_by(barcode="460999").one().name == "Торт вручную"
    response = client.post("/counterparties", data={
        "csrf_token": "token",
        "name": "Клиент с отсрочкой",
        "price_type_id": str(price_type_id),
        "payment_terms_days": "14",
    })
    assert response.status_code == 302
    with app.app_context():
        counterparty = Counterparty.query.filter_by(name="Клиент с отсрочкой").one()
        counterparty.debt = 1000
        db.session.commit()
        counterparty_id = counterparty.id
    response = client.post("/counterparties/transactions", data={
        "csrf_token": "token",
        "counterparty_id": str(counterparty_id),
        "transaction_type": "payment",
        "amount": "600",
        "transaction_date": date.today().isoformat(),
        "note": "Платёжное поручение 1",
    })
    assert response.status_code == 302
    response = client.post("/counterparties/transactions", data={
        "csrf_token": "token",
        "counterparty_id": str(counterparty_id),
        "transaction_type": "refund",
        "amount": "100",
        "transaction_date": date.today().isoformat(),
    })
    assert response.status_code == 302
    with app.app_context():
        counterparty = db.session.get(Counterparty, counterparty_id)
        assert counterparty.payment_terms_days == 14
        assert counterparty.price_type_id == price_type_id
        assert float(counterparty.debt) == 500
        assert ReceivableTransaction.query.count() == 2


def test_point_pricing_gram_recipe_and_representative_return(tmp_path):
    app = make_app(tmp_path)
    seed(app)
    client = app.test_client()
    login(client, "boss")
    with app.app_context():
        rep = User.query.filter_by(username="rep").one()
        counterparty = Counterparty(name="Кондитерская", debt=0)
        retail = PriceType(name="Розница")
        flour = Product(barcode="FLOUR-KG", name="Мука", product_type="raw", unit="кг", calculated_cost=100)
        cake = Product(barcode="CAKE-PCS", name="Торт", product_type="finished", unit="шт", price=1000)
        source = Warehouse(name="Склад сырья", warehouse_type="raw")
        target = Warehouse(name="Склад продукции", warehouse_type="finished")
        db.session.add_all([counterparty, retail, flour, cake, source, target])
        db.session.flush()
        db.session.add(ProductPrice(product_id=cake.id, price_type_id=retail.id, price=900))
        db.session.add(StockBalance(warehouse_id=source.id, product_id=flour.id, quantity=10))
        db.session.commit()
        rep_id, counterparty_id, price_type_id = rep.id, counterparty.id, retail.id
        flour_id, cake_id, source_id, target_id = flour.id, cake.id, source.id, target.id
    response = client.post("/customers", data={
        "csrf_token": "token", "name": "Магазин", "address": "Красная, 1",
        "representative_id": str(rep_id), "counterparty_id": str(counterparty_id),
        "price_type_id": str(price_type_id), "latitude": "45.03547", "longitude": "38.975313",
    })
    assert response.status_code == 302
    with app.app_context():
        customer = Customer.query.filter_by(name="Магазин").one()
        assert customer.price_type_id == price_type_id
        assert customer.latitude == 45.03547
        customer_id = customer.id
        recipe = Recipe(product_id=cake_id, output_quantity=10, labor_cost=10, additional_cost=5, overhead_percent=10)
        db.session.add(recipe)
        db.session.flush()
        db.session.add(RecipeItem(recipe_id=recipe.id, component_id=flour_id, quantity=500, quantity_unit="г", loss_percent=0))
        production = ProductionOrder(number="PRD-GRAM", product_id=cake_id, source_warehouse_id=source_id, warehouse_id=target_id, planned_quantity=10)
        db.session.add(production)
        db.session.commit()
        production_id = production.id
    response = client.post(f"/production/{production_id}/complete", data={"csrf_token": "token", "actual_quantity": "10", "batch_number": "GRAM-1"})
    assert response.status_code == 302
    with app.app_context():
        assert float(StockBalance.query.filter_by(warehouse_id=source_id, product_id=flour_id).one().quantity) == 9.5
        assert float(db.session.get(Product, cake_id).calculated_cost) == 7.15
    login(client, "rep")
    response = client.post(f"/orders/new/{customer_id}", data={"csrf_token": "token", f"qty_{cake_id}": "2"})
    assert response.status_code == 302
    with app.app_context():
        order = Order.query.filter_by(customer_id=customer_id).order_by(Order.id.desc()).first()
        assert float(order.items[0].price) == 900
        order_id, order_item_id = order.id, order.items[0].id
    response = client.post(f"/mobile/returns/new/{order_id}", data={
        "csrf_token": "token", "warehouse_id": str(target_id),
        f"qty_{order_item_id}": "1", "reason": "Повреждение",
    })
    assert response.status_code == 302
    with app.app_context():
        sales_return = SalesReturn.query.filter_by(order_id=order_id).one()
        assert float(sales_return.items[0].quantity) == 1
        assert float(sales_return.total_amount) == 900
