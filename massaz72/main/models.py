from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from massaz72.utils import delete_old_file, get_file_path, validate_file_size


class Certificate(models.Model):
    specialist = models.ForeignKey(
        "cabinet.Specialist",
        on_delete=models.CASCADE,
        related_name="certificates",
        verbose_name="Специалист",
    )
    title = models.CharField("Название", max_length=100)
    image = models.ImageField(
        "Изображение сертификата",
        upload_to=get_file_path,
        validators=[validate_file_size],
    )
    date_received = models.DateField("Дата получения", blank=True, null=True)
    order = models.PositiveIntegerField("Порядок отображения", default=0)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    is_archived = models.BooleanField("В архиве", default=False)

    class Meta:
        verbose_name = "Сертификат"
        verbose_name_plural = "Сертификаты"
        ordering = ["order"]

    def save(self, *args, **kwargs):
        if self.pk:
            delete_old_file(self, "image")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class SiteSettings(models.Model):
    """Модель для хранения основных настроек сайта."""

    head_title = models.CharField(
        verbose_name="Head Title",
        max_length=100,
        default="Детский массаж в Тюмени | Женский массаж",
    )
    main_title = models.CharField(
        verbose_name="Главный заголовок",
        max_length=100,
        default="Детский и женский массаж в Тюмени",
    )
    main_subtitle = models.CharField(
        verbose_name="Главный подзаголовок",
        max_length=100,
        default="Твой массажист - забота о Вашем здоровье",
    )
    meta_description = models.CharField(
        verbose_name="Описание страницы сайта",
        max_length=255,
        default="✅ Детский и женский массаж в Тюмени. Безопасно для детей, расслабляющие процедуры для женщин. Онлайн-запись. Выезд на дом."
    )
    meta_keywords = models.TextField(
        verbose_name="Ключевые слова для поисковых систем",
        default="массаж Тюмень, детский массаж, женский массаж, массаж для детей, массаж для женщин, массаж в Тюмени, онлайн запись, Массаж72, детский массаж Тюмень, женский массаж Тюмень, Тюмень массаж"
    )
    child_massage_title = models.CharField(
        verbose_name="Детский массаж",
        max_length=100,
        default="Детский массаж",
    )
    massage_title = models.CharField(
        verbose_name="Массаж", max_length=100, default="Массаж"
    )
    about_title = models.CharField(
        verbose_name="Обо мне", max_length=100, default="Обо мне"
    )
    contact_title = models.CharField(
        verbose_name="Контакты", max_length=50, default="Контакты"
    )
    background = models.ImageField(
        upload_to=get_file_path,
        verbose_name="Фоновое изображение",
        validators=[validate_file_size],
        blank=True,
        null=True,
    )
    price_change_date = models.DateField(
        "Дата изменения цен",
        blank=True,
        null=True,
        help_text=(
            "Дата, с которой новые цены массажей вступают в силу. "
            "До этой даты на сайте показывается плашка о предстоящем изменении, "
            "а в карточках — текущие цены. Оставьте пустым, если изменение цен не планируется."
        ),
    )
    yandex_verification = models.CharField(
        "Код подтверждения Яндекс.Вебмастер",
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Только значение content из мета-тега (без самого тега). "
            "Яндекс.Вебмастер → добавить сайт → способ «Мета-тег»."
        ),
    )
    google_verification = models.CharField(
        "Код подтверждения Google Search Console",
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Только значение content из HTML-тега (без самого тега). "
            "Search Console → ресурс с префиксом URL → способ «Тег HTML»."
        ),
    )

    reviews_enabled = models.BooleanField(
        "Отзывы включены",
        default=False,
        help_text=(
            "Показывать на сайте секцию отзывов и форму «Оставить отзыв». "
            "При выключении секция и приём новых отзывов скрываются."
        ),
    )
    online_booking_enabled = models.BooleanField(
        "Онлайн-запись включена",
        default=False,
        help_text=(
            "Показывать на сайте страницу онлайн-записи и принимать заявки. "
            "При выключении страница записи и кнопки скрываются."
        ),
    )
    client_cabinet_enabled = models.BooleanField(
        "Личный кабинет клиентов включён",
        default=False,
        help_text=(
            "Разрешить регистрацию, вход и личный кабинет клиентов. "
            "При выключении регистрация и кабинет недоступны."
        ),
    )

    class Meta:
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self):
        return "Настройки"

    def save(self, *args, **kwargs):
        if self.pk:
            delete_old_file(self, "background")
        super().save(*args, **kwargs)


@receiver(pre_delete, sender=Certificate)
def certificate_delete_file(sender, instance, **kwargs):
    """Удаляет файл при удалении объекта Certificate"""
    if instance.image:
        instance.image.delete(False)


@receiver(pre_delete, sender=SiteSettings)
def sitesettings_delete_file(sender, instance, **kwargs):
    """Удаляет файл при удалении объекта SiteSettings"""
    if instance.background:
        instance.background.delete(False)
