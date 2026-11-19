BOOKING_ADMIN_PERMISSIONS = ("booking.view_bookingrequest", "booking.change_bookingrequest")


def is_booking_admin(user):
    """Права просмотра заявок в Django admin, включая право их менять."""
    return bool(
        user and user.is_active and user.is_staff
        and any(user.has_perm(permission) for permission in BOOKING_ADMIN_PERMISSIONS)
    )
