import os

from flask import Flask


web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Bot attivo e funzionante!"


def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)
