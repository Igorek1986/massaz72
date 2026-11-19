from django.contrib.auth import get_user_model


BOOKING_ADMIN_PERMISSIONS = ("booking.view_bookingrequest", "booking.change_bookingrequest")
ERASURE_PERMISSION = "accounts.process_account_erasure"


def is_booking_admin(user):
    """Права просмотра заявок в Django admin, включая право их менять."""
    return bool(
        user and user.is_active and user.is_staff
        and any(user.has_perm(permission) for permission in BOOKING_ADMIN_PERMISSIONS)
    )


def can_process_erasure(user):
    return bool(user and user.is_active and user.has_perm(ERASURE_PERMISSION))


def users_with_permission(permission):
    return get_user_model().objects.with_perm(
        permission, backend="django.contrib.auth.backends.ModelBackend",
    )
