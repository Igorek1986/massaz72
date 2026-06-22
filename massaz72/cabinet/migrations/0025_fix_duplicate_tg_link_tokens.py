"""Чинит баг миграции 0023: AddField(default=callable) вычислил токен один раз
и записал ОДИНАКОВЫЙ tg_link_token всем специалистам. Из-за этого привязка
Telegram уходила первому по сортировке, а не нужному мастеру.

Перегенерируем уникальный токен каждому и сбрасываем ошибочные привязки
(telegram_id), чтобы мастера привязались заново по правильному токену.
"""

import secrets

from django.db import migrations


def regen_tokens(apps, schema_editor):
    Specialist = apps.get_model("cabinet", "Specialist")
    for spec in Specialist.objects.all():
        spec.tg_link_token = secrets.token_urlsafe(16)
        spec.telegram_id = None  # сброс ошибочной привязки (была неоднозначной)
        spec.save(update_fields=["tg_link_token", "telegram_id"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cabinet", "0024_workschedule_notify_end_workschedule_notify_start"),
    ]

    operations = [
        migrations.RunPython(regen_tokens, noop),
    ]
