#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py apply_price_changes
python manage.py collectstatic --noinput

exec gunicorn massaz72.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 15 --keep-alive 5
