"""Developer Contribution Visualizer - Flask application factory."""
from __future__ import annotations

import os

from flask import Flask

from .analytics import Analytics
from .importer import Importer
from .store import Store

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("DCV_DATABASE", os.path.join(BASE_DIR, "data", "dcv.db")),
        CLONE_DIR=os.environ.get("DCV_CLONE_DIR", os.path.join(BASE_DIR, "data", "tmp")),
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)

    store = Store(app.config["DATABASE"])
    app.extensions["dcv"] = {
        "store": store,
        "importer": Importer(store, app.config["CLONE_DIR"]),
        "analytics": Analytics(store),
    }

    from .routes import api, pages
    app.register_blueprint(pages)
    app.register_blueprint(api)
    return app
