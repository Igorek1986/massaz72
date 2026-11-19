from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client as TestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from booking.models import BookingRequest
from cabinet.models import Appointment, AppointmentSeries, Specialist
from main.models import SiteSettings
from reviews.models import Review
from tgbot.models import DialogMessage, PendingNotification, TelegramUser

from .erasure_reminders import send_due_erasure_reminders
from .models import AccountErasureReminder, AccountErasureRequest, Client


class AccountErasureTest(TestCase):
    def setUp(self):
        SiteSettings.objects.create(client_cabinet_enabled=True)
        self.user = get_user_model().objects.create_user("client")
        self.profile = Client.objects.create(
            user=self.user, reminder_enabled=True, telegram_id=200,
        )
        self.operator = get_user_model().objects.create_user("operator")
        self.specialist = Specialist.objects.create(user=self.operator, name="Специалист")
        self.operator.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts", codename="process_account_erasure",
            )
        )
        self.submit_url = reverse("accounts:request_account_erasure")
        self.list_url = reverse("cabinet:erasure_requests")

    def _make_visit(self, **overrides):
        fields = {
            "specialist": self.specialist,
            "client_name": "Тестовый клиент",
            "client_phone": "111",
            "address": "Тестовый адрес",
            "notes": "Тестовые заметки",
            "date": timezone.localdate() - timedelta(days=1),
            "time_start": time(10),
            "cost": Decimal("1500.00"),
            "status": Appointment.COMPLETED,
        }
        fields.update(overrides)
        return Appointment.objects.create(**fields)

    def _make_booking(self, visit):
        return BookingRequest.objects.create(
            user=self.user, source=BookingRequest.Source.ACCOUNT, appointment=visit,
            client_name="Тестовый клиент", preferred_date=visit.date,
            preferred_time=visit.time_start, status=BookingRequest.Status.CONFIRMED,
        )

    def _process_url(self):
        request = AccountErasureRequest.objects.create(user=self.user)
        return request, reverse("cabinet:process_erasure", args=[request.pk])

    def test_request_requires_client_session_post_csrf_and_checkbox(self):
        self.assertEqual(self.client.post(self.submit_url, {"confirm_erasure": "on"}).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.submit_url).status_code, 405)
        self.assertIn("erasure=confirm", self.client.post(self.submit_url)["Location"])
        strict_client = TestClient(enforce_csrf_checks=True)
        strict_client.force_login(self.user)
        response = strict_client.post(self.submit_url, {"confirm_erasure": "on"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AccountErasureRequest.objects.exists())

    def test_request_is_idempotent_and_disables_reminders(self):
        self.client.force_login(self.user)
        for _ in range(2):
            response = self.client.post(self.submit_url, {"confirm_erasure": "on"})
            self.assertIn("#account-erasure", response["Location"])
        self.assertEqual(AccountErasureRequest.objects.filter(user=self.user).count(), 1)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.reminder_enabled)
        self.assertContains(self.client.get(reverse("accounts:profile")), "Запрос принят")
        self.client.force_login(self.operator)
        self.assertContains(self.client.get(self.list_url), "Запросы на удаление ПД (1)")

    def test_staff_with_client_profile_cannot_submit_request(self):
        Client.objects.create(user=self.operator)
        self.client.force_login(self.operator)
        response = self.client.post(self.submit_url, {"confirm_erasure": "on"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AccountErasureRequest.objects.exists())

    def test_staff_permission_and_explicit_confirmation_required(self):
        request, url = self._process_url()
        other = get_user_model().objects.create_user("other_specialist")
        Specialist.objects.create(user=other, name="Другой специалист")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.post(url, {"confirmed": "on"}).status_code, 403)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 400)
        request.refresh_from_db()
        self.assertIsNone(request.completed_at)

    def test_assigned_role_can_review_and_process_without_an_active_specialist_profile(self):
        request, url = self._process_url()
        group = Group.objects.get(name="Ответственный за удаление ПД")
        self.assertEqual(list(group.permissions.values_list("codename", flat=True)), ["process_account_erasure"])
        operator = get_user_model().objects.create_user("erasure-operator-without-profile")
        operator.groups.add(group)
        self.specialist.is_active = False
        self.specialist.save(update_fields=["is_active"])
        for user in (self.operator, operator):
            with self.subTest(has_specialist=user == self.operator):
                self.client.force_login(user)
                self.assertContains(self.client.get(self.list_url), "Запросы на удаление ПД (1)")

        strict = TestClient(enforce_csrf_checks=True)
        strict.force_login(operator)
        self.assertEqual(strict.post(url, {"confirmed": "on"}).status_code, 403)
        self.assertRedirects(self.client.post(url, {"confirmed": "on"}), self.list_url)
        request.refresh_from_db()
        self.assertIsNotNone(request.completed_at)
        self.assertIsNone(request.user_id)

    def test_client_with_erasure_role_cannot_request_removal_of_its_operator_account(self):
        self.user.groups.add(Group.objects.get(name="Ответственный за удаление ПД"))
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.submit_url, {"confirm_erasure": "on"}).status_code, 403)
        self.assertFalse(AccountErasureRequest.objects.exists())

    def test_future_visit_is_anonymized_and_stays_on_schedule(self):
        visit = self._make_visit(
            date=timezone.localdate() + timedelta(days=1), status=Appointment.SCHEDULED,
        )
        original_slot = visit.date, visit.time_start
        self._make_booking(visit)
        request, url = self._process_url()
        self.client.force_login(self.operator)
        self.assertRedirects(self.client.post(url, {"confirmed": "on"}), self.list_url)
        request.refresh_from_db()
        self.assertIsNotNone(request.completed_at)
        visit.refresh_from_db()
        self.assertEqual(visit.client_name, "Клиент удалён")
        self.assertEqual((visit.client_phone, visit.address, visit.notes), ("", "", ""))
        self.assertEqual((visit.date, visit.time_start), original_slot)
        self.assertEqual(visit.status, Appointment.SCHEDULED)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_processing_erases_identity_but_preserves_visit_history(self):
        series = AppointmentSeries.objects.create(specialist=self.specialist, total_sessions=2)
        main = self._make_visit(series=series)
        second = self._make_visit(series=series)
        extra = self._make_visit(parent=second)
        other_visit = self._make_visit()
        booking = self._make_booking(main)
        review = Review.objects.create(author=self.user, name="Клиент", rating=5, text="Тест")
        other_review = Review.objects.create(name="Другой", rating=5, text="Не связан")
        telegram_user = TelegramUser.objects.create(telegram_id=self.profile.telegram_id)
        DialogMessage.objects.create(user=telegram_user, direction=DialogMessage.IN, text="Тест")
        notifications = [
            PendingNotification.objects.create(kind=kind, available_at=timezone.now(), payload=payload)
            for kind, payload in (
                ("new_booking", {"booking_id": booking.pk}),
                ("review", {"review_id": review.pk}),
                ("client_text", {"telegram_id": telegram_user.telegram_id}),
            )
        ]
        other_notice = PendingNotification.objects.create(
            kind="client_text", available_at=timezone.now(), payload={"telegram_id": 100},
        )
        old_session = TestClient()
        old_session.force_login(self.user)
        request, url = self._process_url()
        self.client.force_login(self.operator)

        self.assertRedirects(self.client.post(url, {"confirmed": "on"}), self.list_url)
        request.refresh_from_db()
        self.assertIsNone(request.user_id)
        self.assertIsNotNone(request.completed_at)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Client.objects.filter(pk=self.profile.pk).exists())
        self.assertFalse(BookingRequest.objects.filter(pk=booking.pk).exists())
        self.assertFalse(Review.objects.filter(pk=review.pk).exists())
        self.assertFalse(TelegramUser.objects.filter(pk=telegram_user.pk).exists())
        self.assertFalse(DialogMessage.objects.filter(user=telegram_user).exists())
        self.assertFalse(PendingNotification.objects.filter(pk__in=[n.pk for n in notifications]).exists())
        self.assertTrue(Review.objects.filter(pk=other_review.pk).exists())
        self.assertTrue(PendingNotification.objects.filter(pk=other_notice.pk).exists())
        self.assertIn("/login/", old_session.get(reverse("accounts:profile"))["Location"])
        for visit in (main, second, extra):
            visit.refresh_from_db()
            self.assertEqual(visit.client_name, "Клиент удалён")
            self.assertEqual((visit.client_phone, visit.address, visit.notes), ("", "", ""))
            self.assertEqual(visit.cost, Decimal("1500.00"))
            self.assertIsNone(visit.series_id)
        other_visit.refresh_from_db()
        self.assertEqual(other_visit.client_name, "Тестовый клиент")
        self.client.post(url, {"confirmed": "on"})
        completed_at = AccountErasureRequest.objects.get(pk=request.pk).completed_at
        self.assertEqual(completed_at, request.completed_at)

    def test_shared_telegram_profile_is_left_for_manual_review(self):
        another = get_user_model().objects.create_user("another_client")
        Client.objects.create(user=another, telegram_id=self.profile.telegram_id)
        telegram_user = TelegramUser.objects.create(telegram_id=self.profile.telegram_id)
        _, url = self._process_url()
        self.client.force_login(self.operator)
        self.assertRedirects(self.client.post(url, {"confirmed": "on"}), self.list_url)
        self.assertTrue(TelegramUser.objects.filter(pk=telegram_user.pk).exists())

    def test_operator_can_complete_request_after_manual_review_of_missing_user(self):
        request, url = self._process_url()
        self.user.delete()
        self.client.force_login(self.operator)
        self.assertRedirects(self.client.post(url, {"confirmed": "on"}), self.list_url)
        request.refresh_from_db()
        self.assertIsNotNone(request.completed_at)

    @patch("accounts.erasure_reminders.send_account_erasure_reminder", return_value=True)
    def test_reminders_follow_open_requests_and_staff_permission(self, deliver):
        self.specialist.telegram_id = 123
        self.specialist.save(update_fields=["telegram_id"])
        other = get_user_model().objects.create_user("without_permission")
        Specialist.objects.create(user=other, name="Другой", telegram_id=222)
        no_channel = get_user_model().objects.create_user("without_channel", is_superuser=True)
        Specialist.objects.create(user=no_channel, name="Без канала")
        send_due_erasure_reminders()
        deliver.assert_not_called()

        request = AccountErasureRequest.objects.create(user=self.user)
        send_due_erasure_reminders()
        send_due_erasure_reminders()
        deliver.assert_called_once_with(123)

        AccountErasureReminder.objects.filter(recipient=self.operator).update(
            last_sent_at=timezone.now() - timedelta(days=1),
        )
        send_due_erasure_reminders()
        self.assertEqual(deliver.call_count, 2)

        request.completed_at = timezone.now()
        request.save(update_fields=["completed_at"])
        send_due_erasure_reminders()
        self.assertEqual(deliver.call_count, 2)

    @patch("accounts.erasure_reminders.send_account_erasure_reminder", side_effect=[False, True])
    def test_failed_delivery_can_retry(self, deliver):
        self.specialist.telegram_id = 123
        self.specialist.save(update_fields=["telegram_id"])
        AccountErasureRequest.objects.create(user=self.user)

        send_due_erasure_reminders()
        self.assertIsNone(AccountErasureReminder.objects.get(recipient=self.operator).last_sent_at)
        send_due_erasure_reminders()
        self.assertIsNotNone(AccountErasureReminder.objects.get(recipient=self.operator).last_sent_at)
        self.assertEqual(deliver.call_count, 2)

    @patch("accounts.erasure_reminders.send_account_erasure_reminder", return_value=True)
    def test_new_request_can_notify_again_on_same_day(self, deliver):
        self.specialist.telegram_id = 123
        self.specialist.save(update_fields=["telegram_id"])
        AccountErasureRequest.objects.create(user=self.user)
        send_due_erasure_reminders()

        other = get_user_model().objects.create_user("new_client")
        AccountErasureRequest.objects.create(user=other)
        send_due_erasure_reminders()
        self.assertEqual(deliver.call_count, 2)
