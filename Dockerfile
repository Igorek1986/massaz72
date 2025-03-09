FROM python:3.12

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --upgrade pip && pip install poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-root --no-interaction --no-ansi

COPY massaz72 .

RUN python manage.py collectstatic

CMD ["gunicorn", "massaz72.wsgi:application", "--bind", "0.0.0.0:8000"]
