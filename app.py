"""
Generic bot.
This module defines Flask application,
check signature if SKIP_SIGNATURE is not set in config file, and
launches process function from process_request.py
All changes must occur in other modules
"""
import hashlib
import hmac
import json
import uuid

from flask import Flask, request

import process_request

app = Flask(__name__)
app.config.from_json('config.json')


@app.route("/diagnostics/check", methods=['GET'])
def diagnostic():
    """

    Диагностика работоспособности.

    :return:
    """
    return '', 204


@app.route("/", methods=['GET', 'POST'])
def index():
    """

    Точка входа в приложение.

    :return:
    """
    body = request.data
    signature = request.headers.get('x-pyrus-sig')
    retry = request.headers.get('x-pyrus-retry')
    secret = str.encode(app.config['SECRET_KEY'])
    # Unique session id is generated, useful for log usage
    session_id = str(uuid.uuid4().fields[-1])[:5]

    # If 'skip_signature' in config.json set
    # to true we are skipping checking signature from Pyrus

    # This setting means that we are creating public
    # bot which can be called from several accounts
    if signature:
        is_correct = _is_signature_correct(body, secret, signature)
        if app.config['SKIP_SIGNATURE'] or is_correct:
            body_jsn = json.loads(body.decode('utf-8'))
            return _prepare_response(body_jsn, retry, session_id)
    else:
        return ''


def _is_signature_correct(message, secret, signature):
    digest = hmac.new(secret, msg=message, digestmod=hashlib.sha1).hexdigest()
    return hmac.compare_digest(digest, signature.lower())


def _prepare_response(body, retry, session_id):
    return process_request.process_webhook(body, retry, session_id)


if __name__ == "__main__":
    app.run()
