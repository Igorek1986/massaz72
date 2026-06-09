import secrets

from django.db import models

DEFAULT_WELCOME = (
    "👋 Здравствуйте! Это бот массажиста.\n\n"
    "Напишите, какой массаж вас интересует и удобное время — я передам сообщение "
    "массажисту, и он свяжется с вами.\n\n"
    "Нажмите «💰 Услуги и цены», чтобы посмотреть прайс, "
    "или «📝 Записаться», чтобы оставить заявку."
)

DEFAULT_REQUEST_PROMPT = (
    "Напишите, пожалуйста, одним сообщением:\n"
    "• какой массаж интересует;\n"
    "• желаемые дату и время;\n"
    "• как с вами связаться.\n\n"
    "Я сразу передам заявку массажисту. 🌿"
)


def generate_secret() -> str:
    """Случайный URL-safe секрет для webhook (путь и secret_token)."""
    return secrets.token_urlsafe(24)


class BotSettings(models.Model):
    """Настройки Telegram-бота. Singleton (всегда одна запись, pk=1)."""

    MODE_POLLING = "polling"
    MODE_WEBHOOK = "webhook"
    MODE_CHOICES = [
        (MODE_POLLING, "Polling (опрос Telegram)"),
        (MODE_WEBHOOK, "Webhook"),
    ]

    token = models.CharField(
        "Токен бота",
        max_length=200,
        blank=True,
        default="",
        help_text="Токен, выданный @BotFather.",
    )
    is_enabled = models.BooleanField(
        "Бот включён",
        default=False,
        help_text="Если выключено — webhook не принимает обновления.",
    )
    mode = models.CharField(
        "Режим работы",
        max_length=10,
        choices=MODE_CHOICES,
        default=MODE_POLLING,
        help_text=(
            "Polling — отдельный процесс «manage.py runbot». "
            "Webhook — Telegram сам шлёт обновления на сайт."
        ),
    )
    public_url = models.URLField(
        "Публичный адрес сайта",
        blank=True,
        default="",
        help_text="Напр. https://massaz72.ru — нужен только для режима webhook.",
    )
    secret_path = models.CharField(
        "Секретный путь webhook",
        max_length=64,
        default=generate_secret,
        editable=False,
    )
    secret_token = models.CharField(
        "Секретный токен webhook",
        max_length=64,
        default=generate_secret,
        editable=False,
    )
    bot_username = models.CharField(
        "Имя бота (@)",
        max_length=100,
        blank=True,
        default="",
        editable=False,
    )
    welcome_text = models.TextField(
        "Приветствие (/start)",
        blank=True,
        default=DEFAULT_WELCOME,
    )
    request_prompt = models.TextField(
        "Подсказка при записи",
        blank=True,
        default=DEFAULT_REQUEST_PROMPT,
    )

    class Meta:
        verbose_name = "Настройки Telegram-бота"
        verbose_name_plural = "Настройки Telegram-бота"

    def __str__(self) -> str:
        return "Настройки Telegram-бота"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "BotSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def webhook_url(self) -> str:
        base = self.public_url.rstrip("/")
        if not base:
            return ""
        return f"{base}/tg/webhook/{self.secret_path}/"


class BotAdmin(models.Model):
    """Администратор бота: получает заявки клиентов и отвечает реплаем."""

    telegram_id = models.BigIntegerField(
        "Telegram ID",
        unique=True,
        help_text="Числовой ID. Узнать можно через бота @userinfobot.",
    )
    name = models.CharField(
        "Имя / комментарий",
        max_length=100,
        blank=True,
        default="",
    )
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField("Добавлен", auto_now_add=True)

    class Meta:
        verbose_name = "Администратор бота"
        verbose_name_plural = "Администраторы бота"
        ordering = ["-is_active", "name"]

    def __str__(self) -> str:
        return self.name or str(self.telegram_id)


class TelegramUser(models.Model):
    """Клиент, написавший боту."""

    telegram_id = models.BigIntegerField("Telegram ID", unique=True)
    username = models.CharField("Username", max_length=100, blank=True, default="")
    first_name = models.CharField("Имя", max_length=150, blank=True, default="")
    last_name = models.CharField("Фамилия", max_length=150, blank=True, default="")
    created_at = models.DateTimeField("Первое обращение", auto_now_add=True)
    updated_at = models.DateTimeField("Последняя активность", auto_now=True)

    class Meta:
        verbose_name = "Клиент бота"
        verbose_name_plural = "Клиенты бота"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        if full:
            return full
        if self.username:
            return f"@{self.username}"
        return f"id{self.telegram_id}"


class DialogMessage(models.Model):
    """История переписки клиента и массажиста через бота."""

    IN = "in"
    OUT = "out"
    DIRECTION_CHOICES = [
        (IN, "От клиента"),
        (OUT, "Ответ массажиста"),
    ]

    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Клиент",
    )
    direction = models.CharField("Направление", max_length=3, choices=DIRECTION_CHOICES)
    text = models.TextField("Текст", blank=True, default="")
    admin_telegram_id = models.BigIntegerField(
        "ID ответившего администратора", blank=True, null=True
    )
    created_at = models.DateTimeField("Время", auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Переписка"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_direction_display()}: {self.text[:50]}"


class BookingSessionOption(models.Model):
    """Вариант количества сеансов в мастере записи (настраивается в админке)."""

    count = models.PositiveIntegerField("Количество сеансов")
    label = models.CharField(
        "Метка кнопки",
        max_length=50,
        blank=True,
        default="",
        help_text="Если пусто — отображается «N сеансов».",
    )
    is_active = models.BooleanField("Активна", default=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Вариант кол-ва сеансов"
        verbose_name_plural = "Варианты кол-ва сеансов"
        ordering = ["order", "count"]

    def __str__(self) -> str:
        return self.label if self.label else f"{self.count} сеансов"

    @property
    def button_label(self) -> str:
        return self.label if self.label else f"{self.count} сеансов"


class BookingTimeSlot(models.Model):
    """Временной слот для записи (настраивается в админке)."""

    label = models.CharField("Время (напр. «9:00–12:00»)", max_length=50)
    is_active = models.BooleanField("Активен", default=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Временной слот"
        verbose_name_plural = "Временные слоты"
        ordering = ["order"]

    def __str__(self) -> str:
        return self.label


class AdminForward(models.Model):
    """
    Связь «сообщение, доставленное администратору» → «клиент».
    Когда админ отвечает реплаем на это сообщение, по message_id находим клиента.
    """

    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="forwards",
    )
    admin_telegram_id = models.BigIntegerField()
    admin_message_id = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Пересланное сообщение"
        verbose_name_plural = "Пересланные сообщения"
        constraints = [
            models.UniqueConstraint(
                fields=["admin_telegram_id", "admin_message_id"],
                name="unique_admin_message",
            )
        ]

    def __str__(self) -> str:
        return f"{self.admin_telegram_id}/{self.admin_message_id} → {self.user_id}"
