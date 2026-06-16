from django.core.management.base import BaseCommand

from reviews.models import Review

# (имя, оценка, текст)
APPROVED = [
    ("Ольга", 5, "Ходила на расслабляющий массаж — после первого же сеанса ушло "
                 "напряжение в плечах. Очень внимательный специалист, всё объяснил."),
    ("Марина", 5, "Делала курс массажа спины. Результат превзошёл ожидания: спина "
                  "перестала болеть, осанка стала лучше. Рекомендую!"),
    ("Екатерина", 4, "Приятная атмосфера, аккуратные движения. Немного не хватило "
                     "времени на проработку шеи, но в целом очень довольна."),
    ("Анна", 5, "Привела ребёнка на детский массаж. Малыш не капризничал, мастер "
                "нашёл подход. Спим теперь намного лучше."),
    ("Светлана", 5, "Лучший массаж в Тюмени! Записываюсь уже третий месяц, "
                    "самочувствие отличное."),
]

PENDING = [
    ("Дмитрий", 5, "Отличный антицеллюлитный массаж, заметный эффект уже через "
                   "несколько сеансов. Спасибо!"),
    ("Наталья", 4, "Хороший специалист, всё понравилось. Приду ещё."),
    ("Ирина", 3, "В целом неплохо, но хотелось бы более сильное давление."),
]

REJECTED = [
    ("Реклама", 1, "Купите наш товар по ссылке! Лучшие цены, скидки только сегодня!"),
]


class Command(BaseCommand):
    help = "Создаёт тестовые отзывы (одобренные, на модерации, отклонённые)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="Удалить все существующие отзывы перед созданием тестовых.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted, _ = Review.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Удалено отзывов: {deleted}."))

        created = 0
        for name, rating, text in APPROVED:
            _, was_created = Review.objects.get_or_create(
                name=name, text=text,
                defaults={"rating": rating, "status": Review.Status.APPROVED,
                          "ip_address": "203.0.113.10"},
            )
            created += was_created
        for name, rating, text in PENDING:
            _, was_created = Review.objects.get_or_create(
                name=name, text=text,
                defaults={"rating": rating, "status": Review.Status.PENDING,
                          "ip_address": "203.0.113.20"},
            )
            created += was_created
        for name, rating, text in REJECTED:
            _, was_created = Review.objects.get_or_create(
                name=name, text=text,
                defaults={"rating": rating, "status": Review.Status.REJECTED,
                          "ip_address": "203.0.113.30"},
            )
            created += was_created

        self.stdout.write(self.style.SUCCESS(
            f"Готово. Создано новых отзывов: {created}. "
            f"Всего в базе: {Review.objects.count()} "
            f"(одобрено: {Review.objects.filter(status=Review.Status.APPROVED).count()}, "
            f"на модерации: {Review.objects.filter(status=Review.Status.PENDING).count()}, "
            f"отклонено: {Review.objects.filter(status=Review.Status.REJECTED).count()})."
        ))
