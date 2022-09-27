# based on https://github.com/pypa/sampleproject

import pathlib

from setuptools import find_packages, setup

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="rhub",
    version="0.0.1",
    description="Resource Hub API/backend service",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://github.com/resource-hub-dev/rhub-api",
    author="Red Hat, inc.",
    author_email="resource-hub-dev@redhat.com",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.7, <4",
    install_requires=[
        "alembic",
        "ansible",
        "attrs",
        "celery",
        "click",
        "coloredlogs",
        "connexion[swagger-ui]==2.14.0",  # FIXME https://github.com/spec-first/connexion/commit/cdc8af157dd55cd40b9d60643416ba168ca12b86
        "cron-validator >= 1.0.5",
        "dpath",
        "flask",
        "flask-apscheduler",
        "flask-cors",
        "flask-dotenv",
        "flask_injector",
        "flask-migrate",
        "flask-sqlalchemy",
        "gunicorn",
        "hvac",
        "injector",
        "inotify",
        "jinja2",
        "kombu",
        "openapi_spec_validator < 0.5",  # https://github.com/RonnyPfannschmidt/prance/issues/131
        "openstacksdk",
        "prance[osv]",
        "prometheus_flask_exporter",
        "psycopg2-binary",
        "python-dateutil",
        "python-ironicclient",
        "python-keycloak >=2, <3",
        "pyyaml",
        "requests",
        "SQLAlchemy",
        "tenacity",
        "Werkzeug",
    ],
    extras_require={
        "dev": [
            "build",
            "check-manifest>=0.42",
            "coverage",
            "pip-tools",
            "tox",
        ],
    },
    classifiers=[
        'License :: OSI Approved :: MIT License',
    ],
)
