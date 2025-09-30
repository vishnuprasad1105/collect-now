from __future__ import annotations

import os
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


db = SQLAlchemy()


def create_app(config_object: str = "config.Config") -> Flask:
    if load_dotenv is not None:
        load_dotenv()  # load environment from .env if present
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    # Ensure instance and resource directories exist
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        # Instance path may not be writeable in some environments; fail silently
        pass

    upload_dir = Path(app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)

    resource_dir = Path(app.config["RESOURCE_FOLDER"])
    resource_dir.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    with app.app_context():
        from . import models  # noqa: F401

        db.create_all()

    from .routes import bp as main_bp

    app.register_blueprint(main_bp)

    return app
