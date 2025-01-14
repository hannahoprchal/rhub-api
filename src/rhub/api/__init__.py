import json
import logging
import logging.config
import os
import urllib.parse

import click
import connexion
import flask
import injector
import prance
import psycopg2.errors
import sqlalchemy.exc
from connexion import problem
from flask.cli import with_appcontext
from flask_cors import CORS
from flask_injector import FlaskInjector
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from jinja2 import BaseLoader, Environment
from prometheus_flask_exporter.multiprocess import GunicornInternalPrometheusMetrics
from werkzeug import Response

from rhub import ROOT_PKG_PATH
from rhub.api.vault import Vault, VaultModule
from rhub.auth.keycloak import KeycloakModule
from rhub.messaging import MessagingModule
from rhub.scheduler import SchedulerModule
from rhub.worker import celery


logger = logging.getLogger(__name__)

di = injector.Injector()
db = SQLAlchemy()
migrate = Migrate()
jinja_env = Environment(loader=BaseLoader())

DEFAULT_PAGE_LIMIT = 20


def init_app():
    logger.info('Starting initialization...')
    from ._setup import setup
    setup()
    logger.info('Initialization finished.')


@click.command('init')
@with_appcontext
def init_command():
    init_app()


def log_request():
    try:
        path = flask.request.path.rstrip('/')
        if path == '/v0/openapi.json' or path.startswith('/v0/ui'):
            return

        request_method = flask.request.method
        request_path = flask.request.path
        request_query = urllib.parse.unquote(flask.request.query_string.decode())
        if flask.request.content_type == 'application/json' and flask.request.data:
            request_data = flask.request.json
        else:
            request_data = flask.request.data

        logger.debug(
            f'{request_method=} {request_path=} {request_query=} {request_data=}',
        )

    except Exception:
        logger.exception('Failed to log request (DEBUG logging)')


def log_response(response):
    try:
        path = flask.request.path.rstrip('/')
        if path == '/v0/openapi.json' or path.startswith('/v0/ui'):
            return response

        response_status = response.status
        if response.content_type in {'application/json', 'application/problem+json'}:
            response_data = response.json
            # Don't display secrets in logs.
            for k in response_data:
                if k in {'access_token', 'refresh_token'}:
                    response_data[k] = '***'
        else:
            response_data = response.data

        logger.debug(
            f'{response_status=} {response_data=}',
        )

    except Exception:
        logger.exception('Failed to log response (DEBUG logging)')

    return response


def db_integrity_error_handler(ex: sqlalchemy.exc.IntegrityError):
    connexion_response = None

    try:
        if isinstance(ex.orig, (psycopg2.errors.UniqueViolation,
                                psycopg2.errors.ForeignKeyViolation)):
            msg = ex.orig.diag.message_detail
            connexion_response = problem(400, 'Bad Request', msg)
    except Exception:
        pass

    if connexion_response is None:
        logger.exception(ex)
        connexion_response = problem(500, 'Internal Server Error',
                                     'Unknown database integrity error.')

    return Response(
        response=json.dumps(connexion_response.body, indent=2),
        status=connexion_response.status_code,
        content_type=connexion_response.mimetype,
        headers=connexion_response.headers,
    )


def create_app(extra_config=None):
    """Create Connexion/Flask application."""
    from . import _config

    if _config.LOGGING_CONFIG:
        logging.config.dictConfig(_config.LOGGING_CONFIG)
    else:
        try:
            import coloredlogs
            coloredlogs.install(level=_config.LOGGING_LEVEL)
        except ImportError:
            logger.addHandler(flask.logging.default_handler)
            logger.setLevel(_config.LOGGING_LEVEL)

    connexion_app = connexion.App(__name__)

    flask_app = connexion_app.app
    flask_app.url_map.strict_slashes = False
    if os.getenv('PROMETHEUS_MULTIPROC_DIR'):
        GunicornInternalPrometheusMetrics(flask_app)

    flask_app.config.from_object(_config)
    if extra_config:
        flask_app.config.from_mapping(extra_config)

    parser = prance.ResolvingParser(str(ROOT_PKG_PATH / 'openapi' / 'openapi.yml'))
    connexion_app.add_api(
        parser.specification,
        validate_responses=True,
        strict_validation=True,
        pythonic_params=True,
    )

    connexion_app.add_error_handler(sqlalchemy.exc.IntegrityError,
                                    db_integrity_error_handler)

    # Enable CORS (Cross-Origin Resource Sharing)
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
    CORS(flask_app)

    flask_app.cli.add_command(init_command)

    if logger.isEnabledFor(logging.DEBUG):
        flask_app.before_request(log_request)
        flask_app.after_request(log_response)

    db.init_app(flask_app)
    migrate.init_app(flask_app, db)
    celery.init_app(flask_app)

    RHUB_RETURN_INITIAL_FLASK_APP = os.getenv('RHUB_RETURN_INITIAL_FLASK_APP', 'False')
    if str(RHUB_RETURN_INITIAL_FLASK_APP).lower() == 'true':
        return flask_app

    FlaskInjector(
        app=flask_app,
        injector=di,
        modules=[
            KeycloakModule(flask_app),
            VaultModule(flask_app),
            SchedulerModule(flask_app),
            MessagingModule(flask_app),
        ],
    )

    # Try to retrieve Tower notification webhook creds from vault
    try:
        with flask_app.app_context():
            vault = di.get(Vault)
            webhookCreds = vault.read(flask_app.config['WEBHOOK_VAULT_PATH'])
            if webhookCreds:
                flask_app.config['WEBHOOK_USER'] = webhookCreds['username']
                flask_app.config['WEBHOOK_PASS'] = webhookCreds['password']
            else:
                raise Exception(
                    'Missing tower webhook notification credentials; '
                    f'{vault} {flask_app.config["WEBHOOK_VAULT_PATH"]}'
                )

    except Exception as e:
        logger.error(
            f'Failed to load {flask_app.config["WEBHOOK_VAULT_PATH"]} tower'
            f' webhook notification credentials {e!s}.'
        )

    return flask_app
