FROM python:3.9-slim

ENV PATH=/home/app/.venv/bin:/home/app/.local/bin:${PATH}

RUN python -m pip install --upgrade pip

RUN useradd -U -m app
USER app

WORKDIR /home/app

COPY pyproject.toml poetry.lock ./

RUN python -m pip install --user --upgrade poetry \
    && poetry config virtualenvs.in-project true \
    && poetry install --only main --no-interaction --no-ansi --no-root

COPY . ./

RUN poetry install --no-interaction --no-ansi --only-root

RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "option_wheel_tracker.wsgi", "-b", "0.0.0.0:8000", "--access-logfile", "-"]
