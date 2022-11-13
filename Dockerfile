FROM python:3.9-slim

ENV PATH=/home/option_wheel_tracker/.venv/bin:/home/option_wheel_tracker/.local/bin:${PATH}

RUN python -m pip install --upgrade pip

RUN useradd -U -m option_wheel_tracker
USER option_wheel_tracker

WORKDIR /home/option_wheel_tracker
RUN mkdir /home/option_wheel_tracker/logs

COPY pyproject.toml .
COPY poetry.lock .

RUN python -m pip install --user --upgrade poetry \
    && poetry config virtualenvs.in-project true \
    && poetry install --only main --no-interaction --no-ansi --no-root

RUN poetry install --no-interaction --no-ansi --only-root

COPY manage.py manage.py
COPY worker.py worker.py
COPY catalog catalog
COPY option_wheel_tracker option_wheel_tracker
COPY templates templates

RUN python manage.py collectstatic --noinput

CMD gunicorn option_wheel_tracker.wsgi -b 0.0.0.0:${PORT} --access-logfile -
