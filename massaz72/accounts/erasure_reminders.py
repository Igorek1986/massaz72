from django.db import transaction
from django.utils import timezone

from cabinet.models import Specialist
from tgbot.notifications import send_account_erasure_reminder

from .models import AccountErasureReminder, AccountErasureRequest


def send_due_erasure_reminders():
    pending = AccountErasureRequest.objects.filter(completed_at__isnull=True)
    if not pending.exists():
        return

    recipients = Specialist.objects.filter(
        is_active=True, user__is_active=True, telegram_id__isnull=False,
    ).select_related("user")
    for specialist in recipients:
        if not specialist.user.has_perm("accounts.process_account_erasure"):
            continue
        with transaction.atomic():
            reminder, _ = AccountErasureReminder.objects.select_for_update().get_or_create(
                recipient=specialist.user,
            )
            newest = pending.order_by("-created_at").values_list("created_at", flat=True).first()
            if newest is None:
                return
            now = timezone.now()
            last_sent = reminder.last_sent_at
            already_sent_today = last_sent and timezone.localdate(last_sent) == timezone.localdate(now)
            if already_sent_today and newest <= last_sent:
                continue
            if send_account_erasure_reminder(specialist.telegram_id):
                reminder.last_sent_at = now
                reminder.save(update_fields=["last_sent_at"])
