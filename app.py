"""
SavedFlow Flask application factory + entrypoint.

Run with:
    python app.py
"""
from flask import Flask, render_template

from config import Config
from extensions import init_db
from utils.errors import register_error_handlers

from routes.health import health_bp
from routes.items import items_bp
from routes.imports import imports_bp
from routes.ai import ai_bp
from routes.actions import actions_bp
from routes.recommendations import recommendations_bp
from routes.dashboard import dashboard_bp
from routes.preferences import preferences_bp
from routes.reviews import reviews_bp


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or Config)

    init_db(app)
    register_error_handlers(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(items_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(actions_bp)
    app.register_blueprint(recommendations_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(preferences_bp)
    app.register_blueprint(reviews_bp)

    @app.route("/")
    def index():
        return render_template("test.html")

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5001)