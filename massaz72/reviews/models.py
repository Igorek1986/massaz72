from django.db import models


class ReviewQuerySet(models.QuerySet):
    def public(self):
        """Отзывы, видимые на сайте: одобренные и не в архиве."""
        return self.filter(status=Review.Status.APPROVED, is_archived=False)


class Review(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "На модерации"
        APPROVED = "approved", "Одобрен"
        REJECTED = "rejected", "Отклонён"

    name = models.CharField("Имя", max_length=100)
    rating = models.PositiveSmallIntegerField(
        "Оценка",
        choices=[(i, str(i)) for i in range(1, 6)],
    )
    text = models.TextField("Текст отзыва", max_length=2000)
    status = models.CharField(
        "Статус",
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    ip_address = models.GenericIPAddressField(
        "IP-адрес", null=True, blank=True,
    )
    is_archived = models.BooleanField("В архиве", default=False)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} — {self.rating}★ ({self.get_status_display()})"
