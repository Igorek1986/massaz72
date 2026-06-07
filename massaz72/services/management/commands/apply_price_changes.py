from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from main.models import SiteSettings
from services.models import Massage


class Command(BaseCommand):
    help = (
        "Фиксирует запланированные новые цены массажей: переносит «Новую цену» "
        "в «Стоимость» и очищает дату изменения цен. По умолчанию применяется "
        "только если дата изменения цен уже наступила."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Применить новые цены немедленно, игнорируя дату изменения.",
        )

    def handle(self, *args, **options):
        settings_obj = SiteSettings.objects.first()
        change_date = settings_obj.price_change_date if settings_obj else None
        force = options["force"]

        if not force:
            if not change_date:
                self.stdout.write("Дата изменения цен не задана — нечего применять.")
                return
            if change_date > timezone.localdate():
                self.stdout.write(
                    f"Дата изменения цен ещё не наступила ({change_date:%d.%m.%Y}) — пропуск."
                )
                return

        with transaction.atomic():
            updated = 0
            for massage in Massage.objects.filter(new_price__isnull=False):
                massage.price = massage.new_price
                massage.new_price = None
                massage.save(update_fields=["price", "new_price", "updated_at"])
                updated += 1

            if settings_obj and settings_obj.price_change_date is not None:
                settings_obj.price_change_date = None
                settings_obj.save(update_fields=["price_change_date"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Новые цены применены. Обновлено массажей: {updated}."
            )
        )
