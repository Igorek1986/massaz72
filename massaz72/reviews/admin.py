from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("name", "rating", "status", "is_archived", "created_at")
    list_filter = ("status", "is_archived", "rating")
    search_fields = ("name", "text")
    readonly_fields = ("ip_address", "created_at", "updated_at")
    list_per_page = 50
    actions = ["approve_reviews", "reject_reviews"]
    fieldsets = (
        (None, {"fields": ("name", "rating", "text")}),
        ("Модерация", {"fields": ("status", "is_archived")}),
        ("Служебное", {"fields": ("ip_address", "created_at", "updated_at")}),
    )

    @admin.action(description="Одобрить выбранные отзывы")
    def approve_reviews(self, request, queryset):
        updated = queryset.update(status=Review.Status.APPROVED)
        self.message_user(request, f"Одобрено отзывов: {updated}.")

    @admin.action(description="Отклонить выбранные отзывы")
    def reject_reviews(self, request, queryset):
        updated = queryset.update(status=Review.Status.REJECTED)
        self.message_user(request, f"Отклонено отзывов: {updated}.")
