from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Client as ClientProfile
from booking.models import BookingRequest
from main.models import SiteSettings
from services.models import Massage

PWD = "Sup3rSecret!2026"


def future_date():
    return timezone.localdate() + timedelta(days=2)


def make_massage(name="Спина"):
    return Massage.objects.create(
        name=name, price=Decimal("2000"), duration_min=30, duration_max=60,
        location="Кабинет", massage_type=Massage.ADULT, slug=name.lower(),
    )


class RegistrationTest(TestCase):
    def setUp(self):
        self.settings = SiteSettings.objects.create(client_cabinet_enabled=True)

    def test_register_creates_user_and_client(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "ivan", "password1": PWD, "password2": PWD,
            "phone": "+70000000000", "consent": "on",
        })
        self.assertRedirects(resp, reverse("accounts:dashboard"))
        user = User.objects.get(username="ivan")
        self.assertTrue(hasattr(user, "client_profile"))
        self.assertEqual(user.client_profile.phone, "+70000000000")

    def test_register_links_past_bookings_by_phone(self):
        booking = BookingRequest.objects.create(
            client_name="Иван", phone="+70000000000",
            preferred_date=future_date(), preferred_time=time(10, 0),
        )
        self.client.post(reverse("accounts:register"), {
            "username": "ivan", "password1": PWD, "password2": PWD,
            "phone": "+70000000000", "consent": "on",
        })
        booking.refresh_from_db()
        self.assertEqual(booking.user, User.objects.get(username="ivan"))

    def test_register_disabled_redirects(self):
        self.settings.client_cabinet_enabled = False
        self.settings.save()
        resp = self.client.get(reverse("accounts:register"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(User.objects.count(), 0)


class CabinetTest(TestCase):
    def setUp(self):
        self.settings = SiteSettings.objects.create(client_cabinet_enabled=True)
        self.user = User.objects.create_user("ivan", password=PWD)
        self.profile = ClientProfile.objects.create(user=self.user, phone="111")
        self.massage = make_massage("МойМассаж")
        self.booking = BookingRequest.objects.create(
            client_name="Иван", user=self.user, phone="111", service=self.massage,
            preferred_date=future_date(), preferred_time=time(10, 0),
        )

    def test_login(self):
        resp = self.client.post(reverse("accounts:login"), {
            "username": "ivan", "password": PWD,
        })
        self.assertRedirects(resp, reverse("accounts:dashboard"))

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/account/login", resp["Location"])

    def test_dashboard_shows_only_own(self):
        other = User.objects.create_user("petr", password=PWD)
        ClientProfile.objects.create(user=other)
        BookingRequest.objects.create(
            client_name="Чужой", user=other, service=make_massage("ЧужойМассаж"),
            preferred_date=future_date(), preferred_time=time(9, 0),
        )
        self.client.force_login(self.user)
        body = self.client.get(reverse("accounts:dashboard")).content.decode()
        self.assertIn("МойМассаж", body)
        self.assertNotIn("ЧужойМассаж", body)

    def test_dashboard_shows_calendar_when_sessions(self):
        from booking.models import BookingSessionOption
        from booking.services import confirm_booking
        from cabinet.models import Specialist

        spec = Specialist.objects.create(name="Мастер")
        self.booking.sessions = BookingSessionOption.objects.create(count=3, label="3 сеанса")
        self.booking.save()
        confirm_booking(self.booking, specialist=spec)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.appointment.series.appointments.count(), 3)

        self.client.force_login(self.user)
        body = self.client.get(reverse("accounts:dashboard")).content.decode()
        # Календарь и день-панель присутствуют (детали сеансов грузятся через HTMX).
        self.assertIn("account-calendar", body)
        self.assertIn('id="day-panel"', body)

    def test_events_endpoint(self):
        from booking.models import BookingSessionOption
        from booking.services import confirm_booking
        from cabinet.models import Specialist

        spec = Specialist.objects.create(name="Мастер")
        self.booking.sessions = BookingSessionOption.objects.create(count=3, label="3 сеанса")
        self.booking.save()
        confirm_booking(self.booking, specialist=spec)
        self.client.force_login(self.user)
        data = self.client.get(reverse("accounts:events")).json()
        self.assertEqual(len(data), 3)
        self.assertIn("start", data[0])
        self.assertIn("title", data[0])

    def test_events_requires_login(self):
        resp = self.client.get(reverse("accounts:events"))
        self.assertEqual(resp.status_code, 302)

    def _appointment(self, days_ahead=5):
        from booking.services import confirm_booking
        from cabinet.models import Specialist
        spec = Specialist.objects.create(name="М")
        b = BookingRequest.objects.create(
            client_name="Кл", user=self.user, service=self.massage,
            preferred_date=timezone.localdate() + timedelta(days=days_ahead),
            preferred_time=time(10, 0),
        )
        return confirm_booking(b, specialist=spec)

    def test_day_sessions_shows_own(self):
        apt = self._appointment(5)
        self.client.force_login(self.user)
        body = self.client.get(
            reverse("accounts:day_sessions", args=[apt.date.isoformat()])
        ).content.decode()
        self.assertIn("МойМассаж", body)
        self.assertIn("Перенести", body)
        self.assertIn("Отменить", body)

    def test_cancel_future_session(self):
        apt = self._appointment(5)
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:session_cancel", args=[apt.pk]))
        apt.refresh_from_db()
        self.assertEqual(apt.status, "cancelled")

    def test_cannot_cancel_today_session(self):
        apt = self._appointment(0)  # сегодня
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:session_cancel", args=[apt.pk]))
        apt.refresh_from_db()
        self.assertEqual(apt.status, "scheduled")  # без изменений

    def test_reschedule_creates_request(self):
        from booking.models import RescheduleRequest
        apt = self._appointment(5)
        self.client.force_login(self.user)
        new_date = (timezone.localdate() + timedelta(days=8)).isoformat()
        self.client.post(reverse("accounts:session_reschedule", args=[apt.pk]),
                         {"new_date": new_date, "new_time": "11:00"})
        self.assertTrue(
            RescheduleRequest.objects.filter(appointment=apt, status="pending").exists()
        )

    def test_cancel_pending(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("accounts:cancel_booking", args=[self.booking.pk])
        )
        self.assertRedirects(resp, reverse("accounts:dashboard"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CANCELLED)

    def test_cannot_cancel_others(self):
        other = User.objects.create_user("petr", password=PWD)
        ClientProfile.objects.create(user=other)
        ob = BookingRequest.objects.create(
            client_name="X", user=other,
            preferred_date=future_date(), preferred_time=time(9, 0),
        )
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:cancel_booking", args=[ob.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_cancel_only_pending(self):
        self.booking.status = BookingRequest.Status.CONFIRMED
        self.booking.save()
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:cancel_booking", args=[self.booking.pk]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CONFIRMED)

    def test_profile_update_phone(self):
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:profile"), {
            "save_profile": "1", "phone": "+70000000001",
            "reminder_interval_months": "6",
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.phone, "+70000000001")

    def _configure_bot(self):
        from tgbot.models import BotSettings
        bs = BotSettings.load()
        bs.token = "1:x"
        bs.is_enabled = True
        bs.bot_username = "massaz72_bot"
        bs.save()

    def test_profile_shows_telegram_connect(self):
        self._configure_bot()
        self.client.force_login(self.user)
        body = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn(f"start=acc_{self.profile.link_token}", body)
        self.assertIn("Подключить Telegram", body)

    def test_profile_shows_linked(self):
        self._configure_bot()
        self.profile.telegram_id = 777
        self.profile.telegram_username = "petr"
        self.profile.save()
        self.client.force_login(self.user)
        body = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn("Telegram подключён", body)
        self.assertIn("@petr", body)

    def test_change_password(self):
        self.client.force_login(self.user)
        new = "N3wSecret!2026"
        self.client.post(reverse("accounts:profile"), {
            "change_password": "1", "old_password": PWD,
            "new_password1": new, "new_password2": new,
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))

    def test_reset_request_sent_when_telegram(self):
        from unittest.mock import patch
        self.profile.telegram_id = 777
        self.profile.save()
        with patch("tgbot.notifications.send_password_reset") as m:
            resp = self.client.post(reverse("accounts:password_reset"),
                                    {"username": "ivan"})
        self.assertContains(resp, "отправлена в ваш Telegram")
        m.assert_called_once()

    def test_reset_request_no_telegram(self):
        resp = self.client.post(reverse("accounts:password_reset"),
                                {"username": "ivan"})
        self.assertContains(resp, "не привязан Telegram")

    def test_reset_request_unknown(self):
        resp = self.client.post(reverse("accounts:password_reset"),
                                {"username": "nobody"})
        self.assertContains(resp, "не найден")

    def test_reset_confirm_sets_password(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        new = "N3wReset!2026"
        resp = self.client.post(
            reverse("accounts:password_reset_confirm", args=[uid, token]),
            {"new_password1": new, "new_password2": new},
        )
        self.assertRedirects(resp, reverse("accounts:login") + "?reset=1")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))

    def test_add_months(self):
        from datetime import date
        from accounts.management.commands.send_reminders import add_months
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 6, 15), 6), date(2026, 12, 15))
        self.assertEqual(add_months(date(2026, 8, 15), 12), date(2027, 8, 15))

    def test_send_reminders_due(self):
        from datetime import date, timedelta
        from unittest.mock import patch
        from django.core.management import call_command
        self.profile.telegram_id = 777
        self.profile.reminder_enabled = True
        self.profile.reminder_interval_months = 6
        self.profile.last_reminder_at = date.today() - timedelta(days=210)
        self.profile.save()
        with patch("tgbot.notifications.send_reminder", return_value=True) as m:
            call_command("send_reminders")
        m.assert_called_once_with(777)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_reminder_at, date.today())

    def test_send_reminders_not_due(self):
        from datetime import date, timedelta
        from unittest.mock import patch
        from django.core.management import call_command
        self.profile.telegram_id = 777
        self.profile.reminder_enabled = True
        self.profile.last_reminder_at = date.today() - timedelta(days=10)
        self.profile.save()
        with patch("tgbot.notifications.send_reminder", return_value=True) as m:
            call_command("send_reminders")
        m.assert_not_called()

    def test_send_reminders_skips_no_telegram(self):
        from unittest.mock import patch
        from django.core.management import call_command
        self.profile.reminder_enabled = True
        self.profile.save()  # без telegram_id
        with patch("tgbot.notifications.send_reminder", return_value=True) as m:
            call_command("send_reminders")
        m.assert_not_called()

    def test_reset_confirm_invalid_token(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        resp = self.client.get(
            reverse("accounts:password_reset_confirm", args=[uid, "bad-token"])
        )
        self.assertContains(resp, "недействительна")


class PurgeInactiveTest(TestCase):
    def setUp(self):
        self.massage = make_massage("МойМассаж")

    def _client(self, *, days_inactive, warned_days_ago=None, telegram=None,
                staff=False, username="u"):
        from datetime import date, timedelta
        u = User.objects.create_user(username, password=PWD, is_staff=staff)
        u.last_login = timezone.now() - timedelta(days=days_inactive)
        u.save(update_fields=["last_login"])
        warned = None if warned_days_ago is None else date.today() - timedelta(days=warned_days_ago)
        return ClientProfile.objects.create(
            user=u, telegram_id=telegram, deletion_warned_at=warned,
        )

    def _run(self, **kw):
        from unittest.mock import patch
        from django.core.management import call_command
        with patch("tgbot.notifications.send_deletion_warning", return_value=True) as m:
            call_command("purge_inactive", **kw)
        return m

    def test_active_user_untouched(self):
        c = self._client(days_inactive=10, telegram=111)
        self._run()
        self.assertTrue(User.objects.filter(pk=c.user_id).exists())
        c.refresh_from_db()
        self.assertIsNone(c.deletion_warned_at)

    def test_warns_in_warning_zone(self):
        from datetime import date
        c = self._client(days_inactive=340, telegram=111)
        m = self._run()
        m.assert_called_once_with(111, 30)
        c.refresh_from_db()
        self.assertEqual(c.deletion_warned_at, date.today())
        self.assertTrue(User.objects.filter(pk=c.user_id).exists())

    def test_warns_without_telegram_no_send_but_marks(self):
        from datetime import date
        c = self._client(days_inactive=340, telegram=None)
        m = self._run()
        m.assert_not_called()
        c.refresh_from_db()
        self.assertEqual(c.deletion_warned_at, date.today())

    def test_deletes_after_grace(self):
        c = self._client(days_inactive=400, warned_days_ago=35, telegram=111)
        uid = c.user_id
        self._run()
        self.assertFalse(User.objects.filter(pk=uid).exists())
        self.assertFalse(ClientProfile.objects.filter(pk=c.pk).exists())

    def test_not_deleted_before_grace_passes(self):
        c = self._client(days_inactive=400, warned_days_ago=10, telegram=111)
        self._run()
        self.assertTrue(User.objects.filter(pk=c.user_id).exists())

    def test_reactivated_resets_warning(self):
        c = self._client(days_inactive=5, warned_days_ago=100, telegram=111)
        self._run()
        c.refresh_from_db()
        self.assertIsNone(c.deletion_warned_at)

    def test_staff_never_deleted(self):
        c = self._client(days_inactive=400, warned_days_ago=35, telegram=111, staff=True)
        self._run()
        self.assertTrue(User.objects.filter(pk=c.user_id).exists())

    def test_future_appointment_keeps_account(self):
        from datetime import time
        from booking.models import BookingSessionOption
        from booking.services import confirm_booking
        from cabinet.models import Specialist
        c = self._client(days_inactive=400, warned_days_ago=35, telegram=111)
        spec = Specialist.objects.create(name="Мастер")
        booking = BookingRequest.objects.create(
            client_name="Иван", user=c.user, phone="111", service=self.massage,
            preferred_date=future_date(), preferred_time=time(10, 0),
            sessions=BookingSessionOption.objects.create(count=1, label="1 сеанс"),
        )
        confirm_booking(booking, specialist=spec)
        self._run()
        self.assertTrue(User.objects.filter(pk=c.user_id).exists())
        c.refresh_from_db()
        self.assertIsNone(c.deletion_warned_at)

    def test_dry_run_no_changes(self):
        c = self._client(days_inactive=400, warned_days_ago=35, telegram=111)
        m = self._run(dry_run=True)
        m.assert_not_called()
        self.assertTrue(User.objects.filter(pk=c.user_id).exists())


class SchedulerTest(TestCase):
    def test_ensure_schedules_idempotent(self):
        from django.core.management import call_command
        from django_q.models import Schedule
        call_command("ensure_schedules")
        call_command("ensure_schedules")  # повторный запуск не плодит дубли
        names = set(Schedule.objects.values_list("name", flat=True))
        self.assertEqual(names, {"send_reminders_daily", "purge_inactive_daily"})
        s = Schedule.objects.get(name="send_reminders_daily")
        self.assertEqual(s.func, "accounts.tasks.send_reminders")
        self.assertEqual(s.schedule_type, Schedule.DAILY)
        self.assertEqual(s.next_run.astimezone(timezone.get_current_timezone()).hour, 9)

    def test_task_wrappers_call_commands(self):
        from unittest.mock import patch
        from accounts import tasks
        with patch("accounts.tasks.call_command") as m:
            tasks.send_reminders()
            tasks.purge_inactive()
        self.assertEqual(
            [c.args[0] for c in m.call_args_list],
            ["send_reminders", "purge_inactive"],
        )
