import os
from typing import Any
from dotenv import load_dotenv

from flask import Flask, request, abort, jsonify, Response
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin
from flask_migrate import Migrate

from app.extensions import db
from app.models import BeerDonation
from app.utils import insert_donate, get_sum

admin_ext = Admin(template_mode="bootstrap3")
migrate_ext = Migrate()
_ = load_dotenv()


def create_app(testing: bool = False) -> Flask:
    new_app: Flask = Flask(__name__)
    if testing:
        new_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    else:
        new_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///mydatabase.db"
    new_app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "TypeMeIn")
    db.init_app(new_app)
    migrate_ext.init_app(new_app, db)
    admin_ext.init_app(new_app)

    @new_app.route("/donate", methods=["POST"])
    def payment_page() -> Response:
        data: dict[str, Any] = request.json or {}
        if not data:
            return abort(400)
        try:
            insert_donate(data, db.session)  # pyright: ignore[reportArgumentType]

        except Exception:
            return abort(500)
        return jsonify({"message": "Success"})

    @new_app.route("/balance")
    def get_balance() -> Response:
        # Cast db.session to Session type to satisfy type checker
        total = get_sum(db.session)  # pyright: ignore[reportArgumentType]

        return jsonify({"Total": total})

    return new_app


app = create_app()


class MyModelView(ModelView):
    column_display_all_relations = True
    column_hide_backrefs = False


admin_ext.add_view(MyModelView(BeerDonation, db.session))
