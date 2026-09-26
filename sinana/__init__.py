import os
import secrets
from pathlib import Path

from flask import Flask, abort, redirect, request, session, url_for
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SINANA_SECRET_KEY", "change-this-key-on-server"),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "SINANA_DATABASE_URL",
            f"sqlite:///{Path(app.instance_path) / 'sinana.db'}",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=12 * 1024 * 1024,
        UPLOAD_FOLDER=str(Path(app.instance_path) / "uploads"),
        ONE_C_API_TOKEN=os.getenv("SINANA_1C_API_TOKEN", ""),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Войдите в приложение"

    from .models import User
    from .routes import api, auth, main

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(api, url_prefix="/api/1c")
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def protect_roles_and_csrf():
        if request.method == "POST" and not (request.endpoint or "").startswith("api."):
            expected = session.get("csrf_token")
            supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not expected or not secrets.compare_digest(expected, supplied or ""):
                abort(400, "Недействительный защитный токен")
        if not current_user.is_authenticated:
            return None
        if not current_user.is_active_user:
            from flask_login import logout_user

            logout_user()
            return redirect(url_for("auth.login"))
        if session.get("user_session_version") != current_user.session_version:
            from flask_login import logout_user

            logout_user()
            session.clear()
            return redirect(url_for("auth.login"))
        if request.endpoint == "main.dashboard" and current_user.role == "representative":
            return redirect(url_for("main.mobile"))
        return None

    @app.context_processor
    def inject_csrf():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return {"csrf_token": token}

    @app.cli.command("init-admin")
    def init_admin():
        """Create the first manager from SINANA_ADMIN_* environment variables."""
        username = os.getenv("SINANA_ADMIN_LOGIN")
        password = os.getenv("SINANA_ADMIN_PASSWORD")
        full_name = os.getenv("SINANA_ADMIN_NAME", "Руководитель")
        if not username or not password or len(password) < 8:
            raise RuntimeError("Set SINANA_ADMIN_LOGIN and SINANA_ADMIN_PASSWORD (8+ chars)")
        with app.app_context():
            db.create_all()
            if User.query.filter_by(username=username).first():
                print("Administrator already exists")
                return
            user = User(username=username, full_name=full_name, role="manager")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            print(f"Administrator {username} created")

    with app.app_context():
        db.create_all()
    return app
