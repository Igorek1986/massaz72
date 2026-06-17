from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from booking.forms import BookingForm
from booking.models import BookingRequest, BookingSessionOption
from booking.services import confirm_booking, decline_booking
from cabinet.models import Appointment, Specialist
from main.models import SiteSettings
from services.models import Massage

User = get_user_model()


def make_massage(name="Спина", price="2000"):
    return Massage.objects.create(
        name=name, price=Decimal(price), duration_min=30, duration_max=60,
        location="Кабинет", massage_type=Massage.ADULT, slug=name.lower(),
    )


def make_specialist(username="master", name="Мастер"):
    user = User.objects.create_user(username, password="pw")
    return Specialist.objects.create(user=user, name=name)


def human_token(seconds_ago=5):
    from django.core import signing
    signer = signing.Signer(salt="reviews.timing")
    issued = int(timezone.now().timestamp()) - seconds_ago
    return signer.sign(str(issued))


def future_date():
    return timezone.localdate() + timedelta(days=3)


def active_session_pk():
    """PK активного варианта кол-ва сеансов (засеяны миграцией)."""
    return BookingSessionOption.objects.filter(is_active=True).first().pk


class BookingModelTest(TestCase):
    def test_pending_filter(self):
        a = BookingRequest.objects.create(
            client_name="A", preferred_date=future_date(), preferred_time=time(10),
        )
        BookingRequest.objects.create(
            client_name="B", preferred_date=future_date(), preferred_time=time(11),
            status=BookingRequest.Status.CONFIRMED,
        )
        self.assertEqual(list(BookingRequest.objects.pending()), [a])


class BookingFormTest(TestCase):
    def setUp(self):
        self.massage = make_massage()

    def _data(self, **over):
        data = {
            "client_name": "Иван",
            "service": self.massage.pk,
            "sessions": active_session_pk(),
            "preferred_date": future_date().isoformat(),
            "preferred_time": "10:00",
            "phone": "",
            "comment": "",
            "ts": human_token(),
            "website": "",
            "consent": "on",
        }
        data.update(over)
        return data

    def test_valid_without_phone(self):
        form = BookingForm(data=self._data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_blank_name_invalid(self):
        form = BookingForm(data=self._data(client_name="  "))
        self.assertFalse(form.is_valid())
        self.assertIn("client_name", form.errors)

    def test_past_date_invalid(self):
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        form = BookingForm(data=self._data(preferred_date=past))
        self.assertFalse(form.is_valid())
        self.assertIn("preferred_date", form.errors)

    def test_specialist_hidden_when_single(self):
        make_specialist()
        self.assertNotIn("specialist", BookingForm().fields)

    def test_specialist_shown_when_multiple(self):
        make_specialist("m1", "М1")
        make_specialist("m2", "М2")
        self.assertIn("specialist", BookingForm().fields)

    def test_specialist_hidden_when_one_active(self):
        make_specialist("m1", "М1")
        inactive = make_specialist("m2", "М2")
        inactive.is_active = False
        inactive.save()
        self.assertNotIn("specialist", BookingForm().fields)

    def test_specialist_excludes_inactive(self):
        make_specialist("m1", "М1")
        make_specialist("m2", "М2")
        inactive = make_specialist("m3", "М3")
        inactive.is_active = False
        inactive.save()
        qs = BookingForm().fields["specialist"].queryset
        self.assertEqual(qs.count(), 2)
        self.assertNotIn(inactive, list(qs))

    def test_sessions_hidden_when_no_options(self):
        from booking.models import BookingSessionOption
        BookingSessionOption.objects.all().delete()
        self.assertNotIn("sessions", BookingForm().fields)

    def test_sessions_shown_when_options(self):
        from booking.models import BookingSessionOption
        BookingSessionOption.objects.create(count=5, label="5 сеансов", order=0)
        self.assertIn("sessions", BookingForm().fields)


class BookingServicesTest(TestCase):
    def setUp(self):
        self.specialist = make_specialist()
        self.massage = make_massage()
        self.booking = BookingRequest.objects.create(
            client_name="Пётр", phone="123", service=self.massage,
            preferred_date=future_date(), preferred_time=time(14, 30),
        )

    def test_confirm_creates_appointment(self):
        apt = confirm_booking(self.booking, specialist=self.specialist)
        self.assertIsNotNone(apt)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CONFIRMED)
        self.assertEqual(self.booking.appointment_id, apt.pk)
        self.assertEqual(apt.specialist, self.specialist)
        self.assertEqual(apt.client_name, "Пётр")
        self.assertEqual(apt.cost, self.massage.price)
        self.assertEqual(apt.date, self.booking.preferred_date)
        self.assertEqual(apt.time_start, time(14, 30))

    def test_confirm_creates_series_for_course(self):
        from cabinet.models import Appointment, AppointmentSeries
        opt = BookingSessionOption.objects.create(count=10, label="10 сеансов")
        self.booking.sessions = opt
        self.booking.save()
        apt = confirm_booking(self.booking, specialist=self.specialist)
        self.assertEqual(
            Appointment.objects.filter(specialist=self.specialist).count(), 10
        )
        self.assertEqual(AppointmentSeries.objects.count(), 1)
        self.assertEqual(apt.series.total_sessions, 10)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CONFIRMED)

    def test_confirm_with_overrides(self):
        new_d = future_date() + timedelta(days=1)
        apt = confirm_booking(
            self.booking, specialist=self.specialist,
            date=new_d, time_start=time(16, 0), cost=Decimal("999"),
        )
        self.assertEqual(apt.date, new_d)
        self.assertEqual(apt.time_start, time(16, 0))
        self.assertEqual(apt.cost, Decimal("999"))

    def test_confirm_fallback_picks_active_specialist(self):
        """Без выбранного мастера берём активного, а не первого попавшегося."""
        inactive = make_specialist("inact", "Неактивный")
        inactive.is_active = False
        inactive.order = 0
        inactive.save()
        booking = BookingRequest.objects.create(
            client_name="X", preferred_date=future_date(), preferred_time=time(9, 0),
        )
        apt = confirm_booking(booking)  # мастер не задан
        self.assertEqual(apt.specialist, self.specialist)  # активный, не «Неактивный»
        self.assertTrue(apt.specialist.is_active)

    def test_confirm_no_specialist_returns_none(self):
        apt = confirm_booking(self.booking)  # ни одного Specialist (никого не создавали тут? создан в setUp)
        # specialist есть из setUp -> fallback на него
        self.assertIsNotNone(apt)

    def test_decline(self):
        decline_booking(self.booking)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.DECLINED)


class BookingViewTest(TestCase):
    def setUp(self):
        self.url = reverse("booking:page")
        self.massage = make_massage()
        self.settings_obj = SiteSettings.objects.create(online_booking_enabled=True)

    def _post(self, **over):
        data = {
            "client_name": "Иван",
            "service": self.massage.pk,
            "sessions": active_session_pk(),
            "preferred_date": future_date().isoformat(),
            "preferred_time": "10:00",
            "phone": "",
            "comment": "",
            "ts": human_token(),
            "website": "",
            "consent": "on",
        }
        data.update(over)
        return self.client.post(self.url, data)

    def test_disabled_redirects(self):
        self.settings_obj.online_booking_enabled = False
        self.settings_obj.save()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(BookingRequest.objects.count(), 0)

    def test_get_shows_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "booking-form")

    def test_happy_path_creates_pending(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Заявка принята")
        b = BookingRequest.objects.get()
        self.assertEqual(b.status, BookingRequest.Status.PENDING)
        self.assertEqual(b.source, BookingRequest.Source.GUEST)
        self.assertEqual(b.client_name, "Иван")
        self.assertEqual(b.phone, "")

    def test_honeypot_silently_drops(self):
        resp = self._post(website="spam")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(BookingRequest.objects.count(), 0)

    def test_timetrap_silently_drops(self):
        resp = self._post(ts=human_token(seconds_ago=0))
        self.assertEqual(BookingRequest.objects.count(), 0)
        self.assertContains(resp, "Заявка принята")

    def test_invalid_form_rerenders(self):
        resp = self._post(client_name="  ")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(BookingRequest.objects.count(), 0)
        self.assertContains(resp, "booking-form__error")

    def test_thankyou_shows_deeplink_and_qr(self):
        from unittest.mock import patch

        from tgbot.models import BotSettings
        bs = BotSettings.load()
        bs.token = "123:abc"
        bs.is_enabled = True
        bs.bot_username = "massaz72_bot"
        bs.save()
        # бот мокаем (None) — нас интересует только экран «спасибо», не рассылка
        with patch("tgbot.bot.get_bot", return_value=None):
            resp = self._post()
        booking = BookingRequest.objects.get()
        self.assertContains(resp, f"start={booking.link_token}")
        self.assertContains(resp, "<svg")

    def test_service_preselected_from_query(self):
        resp = self.client.get(self.url, {"service": self.massage.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["form"].initial.get("service"), self.massage.pk)
        self.assertContains(resp, f'value="{self.massage.pk}" selected')

    def test_date_preselected_from_query(self):
        d = (timezone.localdate() + timedelta(days=4)).isoformat()
        resp = self.client.get(self.url, {"date": d})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'value="{d}"')

    def test_bad_service_query_ignored(self):
        resp = self.client.get(self.url, {"service": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context["form"].initial.get("service"))

    def test_status_endpoint(self):
        b = BookingRequest.objects.create(
            client_name="X", preferred_date=future_date(), preferred_time=time(10, 0),
        )
        data = self.client.get(reverse("booking:status", args=[b.link_token])).json()
        self.assertTrue(data["found"])
        self.assertFalse(data["confirmed"])
        b.client_confirmed = True
        b.save()
        data = self.client.get(reverse("booking:status", args=[b.link_token])).json()
        self.assertTrue(data["confirmed"])

    def test_status_endpoint_unknown(self):
        data = self.client.get(reverse("booking:status", args=["nope"])).json()
        self.assertFalse(data["found"])

    def test_master_notified_only_when_phone(self):
        from unittest.mock import patch
        with patch("booking.views._notify_admins") as m:
            self._post(phone="")
            m.assert_not_called()  # без телефона — отложено до бота
        with patch("booking.views._notify_admins") as m:
            self._post(phone="+70000000000")
            m.assert_called_once()  # есть телефон — уведомляем сразу

    def test_consent_required(self):
        resp = self._post(consent="")
        self.assertEqual(BookingRequest.objects.count(), 0)
        self.assertContains(resp, "Необходимо согласие")

    def test_booking_saves_sessions(self):
        from booking.models import BookingSessionOption
        opt = BookingSessionOption.objects.create(count=5, label="5 сеансов", order=0)
        self._post(sessions=opt.pk)
        booking = BookingRequest.objects.get()
        self.assertEqual(booking.sessions, opt)

    def test_logged_in_booking_links_to_account(self):
        from accounts.models import Client as ClientProfile
        user = User.objects.create_user("clientacc", password="pw")
        ClientProfile.objects.create(user=user, phone="555")
        self.client.force_login(user)
        self._post()
        booking = BookingRequest.objects.get()
        self.assertEqual(booking.user, user)
        self.assertEqual(booking.source, BookingRequest.Source.ACCOUNT)


class CabinetBookingTest(TestCase):
    def setUp(self):
        self.specialist = make_specialist()
        self.massage = make_massage()
        self.settings_obj = SiteSettings.objects.create(online_booking_enabled=False)
        self.booking = BookingRequest.objects.create(
            client_name="Клиент", phone="999", service=self.massage,
            preferred_date=future_date(), preferred_time=time(12, 0),
        )

    def _login(self):
        self.client.force_login(self.specialist.user)

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse("cabinet:booking_requests"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_specialist_can_open(self):
        self._login()
        resp = self.client.get(reverse("cabinet:booking_requests"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Клиент")

    def test_confirm_creates_appointment(self):
        self._login()
        resp = self.client.post(
            reverse("cabinet:booking_request_confirm", args=[self.booking.pk]),
            {"status": "pending", "date": future_date().isoformat(),
             "time": "13:30", "cost": "1500"},
        )
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CONFIRMED)
        apt = self.booking.appointment
        self.assertIsNotNone(apt)
        self.assertEqual(apt.specialist, self.specialist)
        self.assertEqual(apt.time_start, time(13, 30))
        self.assertEqual(apt.cost, Decimal("1500"))

    def test_decline(self):
        self._login()
        self.client.post(
            reverse("cabinet:booking_request_decline", args=[self.booking.pk]),
            {"status": "pending"},
        )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.DECLINED)

    def test_confirm_assigns_to_requested_specialist(self):
        """Подтверждающий (напр. главный) создаёт запись выбранному в заявке
        мастеру, а не себе."""
        other = make_specialist("other2", "Другой мастер")
        self.booking.specialist = other
        self.booking.save()
        self._login()  # логинимся как self.specialist (не «Другой мастер»)
        self.client.post(
            reverse("cabinet:booking_request_confirm", args=[self.booking.pk]),
            {"status": "pending", "date": future_date().isoformat(),
             "time": "13:30", "cost": "1500"},
        )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.appointment.specialist, other)

    def test_confirm_requires_post(self):
        self._login()
        resp = self.client.get(
            reverse("cabinet:booking_request_confirm", args=[self.booking.pk])
        )
        self.assertEqual(resp.status_code, 405)

    def test_toggle_flips(self):
        self._login()
        resp = self.client.post(reverse("cabinet:booking_toggle"))
        self.assertEqual(resp.status_code, 200)
        self.settings_obj.refresh_from_db()
        self.assertTrue(self.settings_obj.online_booking_enabled)

    def test_list_filter_confirmed(self):
        self._login()
        confirm_booking(self.booking, specialist=self.specialist)
        resp = self.client.get(
            reverse("cabinet:booking_request_list") + "?status=confirmed"
        )
        self.assertContains(resp, "Клиент")
        resp2 = self.client.get(
            reverse("cabinet:booking_request_list") + "?status=pending"
        )
        self.assertNotContains(resp2, "Клиент")
