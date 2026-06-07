#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py apply_price_changes
python manage.py collectstatic --noinput

# Фоновая «уборка»: раз в несколько часов переносит запланированную цену в основную,
# когда дата изменения наступила. Сам момент смены цены на сайте обеспечивается
# динамически (в полночь по Тюмени), поэтому точное время запуска здесь неважно.
# Команда сама сверяет дату с settings.TIME_ZONE и ничего не делает, пока дата не пришла,
# — поэтому привязки к часовому поясу в этом скрипте нет.
(
  while true; do
    sleep 21600   # раз в 6 часов
    python manage.py apply_price_changes || true
  done
) &

exec gunicorn massaz72.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 15 --keep-alive 5
