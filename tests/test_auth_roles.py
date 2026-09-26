from sinana import create_app, db
from sinana.models import User


def make_app(tmp_path):
    return create_app({"TESTING": True, "SECRET_KEY": "test", "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}"})


def add_user(app, username, role):
    with app.app_context():
        user = User(username=username, full_name=username.title(), role=role)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()


def csrf(client):
    with client.session_transaction() as session:
        session["csrf_token"] = "token"
    return "token"


def test_roles_have_different_start_pages(tmp_path):
    app = make_app(tmp_path)
    add_user(app, "boss", "manager")
    add_user(app, "rep", "representative")
    client = app.test_client()
    token = csrf(client)
    response = client.post("/login", data={"username": "boss", "password": "password123", "csrf_token": token})
    assert response.headers["Location"].endswith("/")
    client.post("/logout", data={"csrf_token": token})
    response = client.post("/login", data={"username": "rep", "password": "password123", "csrf_token": token})
    assert response.headers["Location"].endswith("/mobile")
    assert client.get("/team").status_code == 403

