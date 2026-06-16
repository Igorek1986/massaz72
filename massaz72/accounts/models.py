from django.conf import settings
from django.db import models


class Client(models.Model):
    """Профиль клиента. Аккаунт первичен, вход — стандартный Django User.
    Телефон необязателен; привязка к боту/мессенджеру — на будущее (Этап 3)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_profile",
        verbose_name="Пользователь",
    )
    phone = models.CharField("Телефон", max_length=20, blank=True, default="")
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"

    def __str__(self) -> str:
        return self.user.get_username()
