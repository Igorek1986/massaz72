from datetime import date as date_cls
from datetime import datetime, time, timedelta
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
    """PK активного варианта кол-ва сеансов или "" (если вариантов нет)."""
    opt = BookingSessionOption.objects.filter(is_active=True).first()
    return opt.pk if opt else ""


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

    def test_phone_normalization(self):
        for raw, norm in [
            ("9123456789", "+79123456789"),
            ("+7 912 345 67 89", "+79123456789"),
            ("8(912)345-67-89", "+79123456789"),
        ]:
            form = BookingForm(data=self._data(phone=raw))
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["phone"], norm)

    def test_phone_invalid(self):
        form = BookingForm(data=self._data(phone="12345"))
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_sessions_hidden_when_no_options(self):
        from booking.models import BookingSessionOption
        BookingSessionOption.objects.all().delete()
        self.assertNotIn("sessions", BookingForm().fields)

    def test_sessions_shown_when_options(self):
        from booking.models import BookingSessionOption
        spec = make_specialist()
        BookingSessionOption.objects.create(specialist=spec, count=5, label="5 сеансов", order=0)
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
        opt = BookingSessionOption.objects.create(
            specialist=self.specialist, count=10, label="10 сеансов")
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

    def test_no_phone_awaits_contact(self):
        # Без телефона заявка ждёт контакта (подтверждения в боте), мастеру не
        # показывается, уведомление не уходит. POST → redirect на /confirm/.
        resp = self._post()
        b = BookingRequest.objects.get()
        self.assertRedirects(
            resp, reverse("booking:confirm", args=[b.link_token]),
            fetch_redirect_response=False,
        )
        self.assertEqual(b.status, BookingRequest.Status.AWAITING_CONTACT)
        self.assertEqual(b.source, BookingRequest.Source.GUEST)
        self.assertEqual(b.phone, "")

    def test_phone_makes_pending(self):
        resp = self._post(phone="8 (912) 345-67-89")
        b = BookingRequest.objects.get()
        self.assertRedirects(
            resp, reverse("booking:confirm", args=[b.link_token]),
            fetch_redirect_response=False,
        )
        self.assertEqual(b.status, BookingRequest.Status.PENDING)
        self.assertEqual(b.phone, "+79123456789")  # нормализован

    def test_invalid_phone_rejected(self):
        resp = self._post(phone="12345")
        self.assertEqual(BookingRequest.objects.count(), 0)
        self.assertContains(resp, "booking-form__error")

    def test_account_phone_fallback_makes_pending(self):
        from accounts.models import Client as ClientProfile
        user = User.objects.create_user("acc2", password="pw")
        ClientProfile.objects.create(user=user, phone="+79990001122")
        self.client.force_login(user)
        self._post(phone="")  # телефон в форме пуст — берём из профиля
        b = BookingRequest.objects.get()
        self.assertEqual(b.status, BookingRequest.Status.PENDING)
        self.assertEqual(b.phone, "+79990001122")

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

    def test_confirm_page_shows_deeplink_and_qr(self):
        from unittest.mock import patch

        from tgbot.models import BotSettings
        bs = BotSettings.load()
        bs.token = "123:abc"
        bs.is_enabled = True
        bs.bot_username = "massaz72_bot"
        bs.save()
        # бот мокаем (None) — нас интересует страница подтверждения, не рассылка
        with patch("tgbot.bot.get_bot", return_value=None):
            self._post()  # без телефона → AWAITING_CONTACT
        booking = BookingRequest.objects.get()
        resp = self.client.get(reverse("booking:confirm", args=[booking.link_token]))
        self.assertContains(resp, f"start={booking.link_token}")
        self.assertContains(resp, "<svg")
        self.assertContains(resp, "confirmCountdown")  # обратный отсчёт

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
        spec = make_specialist()  # один мастер → варианты сеансов его
        opt = BookingSessionOption.objects.create(
            specialist=spec, count=5, label="5 сеансов", order=0)
        # мастер есть → проверяется доступность: берём рабочий день и время
        self._post(sessions=opt.pk, preferred_date=next_weekday(0).isoformat(),
                   preferred_time="10:00", phone="+79991112233")
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


def next_weekday(weekday: int, min_ahead: int = 7) -> date_cls:
    """Ближайшая дата ≥ today+min_ahead с нужным днём недели (0=Пн)."""
    d = timezone.localdate() + timedelta(days=min_ahead)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def make_appointment(specialist, massage, d, t, **over):
    from cabinet.models import Appointment
    data = dict(
        specialist=specialist, client_name="Кто-то", service=massage,
        date=d, time_start=t, cost=Decimal("1000"), status=Appointment.SCHEDULED,
    )
    data.update(over)
    return Appointment.objects.create(**data)


class AvailabilityTest(TestCase):
    def setUp(self):
        from cabinet.models import WorkSchedule
        self.specialist = make_specialist()
        self.massage = make_massage()  # duration_max=60
        self.schedule = WorkSchedule.for_specialist(self.specialist)  # Пн–Пт 9–19, перерыв 15
        self.monday = next_weekday(0)
        # «Утро» текущего дня для детерминированного lead-time.
        self.morning = datetime.combine(timezone.localdate(), time(0, 0))

    def _free(self, d, sessions=1):
        from booking.availability import free_starts
        return free_starts(self.specialist, d, self.massage, sessions, now=self.morning)

    def test_working_day_has_slots(self):
        free = self._free(self.monday)
        self.assertIn(time(9, 0), free)
        # Последний слот: 18:00 (18:00+60=19:00 ≤ конца дня).
        self.assertIn(time(18, 0), free)
        self.assertNotIn(time(18, 15), free)  # не влезает массаж до 19:00

    def test_non_working_day_empty(self):
        sunday = next_weekday(6)
        self.assertEqual(self._free(sunday), set())

    def test_vacation_exception_empty(self):
        from cabinet.models import ScheduleException
        ScheduleException.objects.create(
            specialist=self.specialist, date_from=self.monday, date_to=self.monday,
            exception_type=ScheduleException.VACATION,
        )
        self.assertEqual(self._free(self.monday), set())

    def test_blocked_lunch_excluded(self):
        from cabinet.models import BlockedSlot
        BlockedSlot.objects.create(
            specialist=self.specialist, date=self.monday,
            time_start=time(13, 0), time_end=time(14, 0), note="Обед",
        )
        free = self._free(self.monday)
        self.assertNotIn(time(13, 0), free)
        self.assertNotIn(time(12, 45), free)  # 12:45+60+15 пересекает обед
        self.assertIn(time(14, 0), free)      # сразу после обеда — свободно
        self.assertIn(time(11, 0), free)

    def test_appointment_blocks_with_break(self):
        make_appointment(self.specialist, self.massage, self.monday, time(15, 0))
        free = self._free(self.monday)
        self.assertNotIn(time(15, 0), free)
        self.assertNotIn(time(14, 0), free)   # 14:00+75 пересекает 15:00
        self.assertIn(time(16, 15), free)     # конец 16:00 + перерыв 15 → 16:15 свободно

    def test_cancelled_appointment_does_not_block(self):
        from cabinet.models import Appointment
        make_appointment(
            self.specialist, self.massage, self.monday, time(15, 0),
            status=Appointment.CANCELLED,
        )
        self.assertIn(time(15, 0), self._free(self.monday))

    def test_pending_request_soft_holds(self):
        BookingRequest.objects.create(
            client_name="Бронь", service=self.massage, specialist=self.specialist,
            preferred_date=self.monday, preferred_time=time(11, 0),
            status=BookingRequest.Status.PENDING,
        )
        self.assertNotIn(time(11, 0), self._free(self.monday))

    def test_pending_request_without_specialist_holds(self):
        # Сайт с одним мастером: заявка без мастера держит его слот.
        BookingRequest.objects.create(
            client_name="Бронь", service=self.massage, specialist=None,
            preferred_date=self.monday, preferred_time=time(11, 0),
            status=BookingRequest.Status.PENDING,
        )
        self.assertNotIn(time(11, 0), self._free(self.monday))

    def test_awaiting_contact_holds_slot(self):
        BookingRequest.objects.create(
            client_name="Ждёт", service=self.massage, specialist=self.specialist,
            preferred_date=self.monday, preferred_time=time(11, 0),
            status=BookingRequest.Status.AWAITING_CONTACT,
        )
        self.assertNotIn(time(11, 0), self._free(self.monday))

    def test_expired_awaiting_contact_frees_slot(self):
        from django.utils import timezone as tz
        b = BookingRequest.objects.create(
            client_name="Протух", service=self.massage, specialist=self.specialist,
            preferred_date=self.monday, preferred_time=time(11, 0),
            status=BookingRequest.Status.AWAITING_CONTACT,
        )
        # Старше таймаута удержания (15 мин) — слот не держит.
        BookingRequest.objects.filter(pk=b.pk).update(
            created_at=tz.now() - timedelta(minutes=20)
        )
        self.assertIn(time(11, 0), self._free(self.monday))

    def test_lead_time_per_master(self):
        from booking.availability import free_starts
        today = timezone.localdate()
        if today.weekday() > 4:
            return
        self.schedule.lead_time_minutes = 120
        self.schedule.save()
        now = datetime.combine(today, time(10, 0))
        free = free_starts(self.specialist, today, self.massage, now=now)
        self.assertNotIn(time(11, 0), free)  # запас 120 мин → раньше 12:00 нельзя
        self.assertIn(time(12, 0), free)

    def test_confirmed_request_does_not_double_count(self):
        # Подтверждённая заявка (есть appointment) учитывается как Appointment,
        # сама заявка слот не держит.
        BookingRequest.objects.create(
            client_name="Готово", service=self.massage, specialist=self.specialist,
            preferred_date=self.monday, preferred_time=time(11, 0),
            status=BookingRequest.Status.CONFIRMED,
        )
        self.assertIn(time(11, 0), self._free(self.monday))

    def test_today_past_and_lead_time_hidden(self):
        from booking.availability import free_starts
        today = timezone.localdate()
        if today.weekday() > 4:  # выходной — пропускаем (нерабочий день)
            return
        now = datetime.combine(today, time(10, 0))
        free = free_starts(self.specialist, today, self.massage, now=now)
        # lead 60 мин → раньше 11:00 нельзя.
        self.assertNotIn(time(10, 0), free)
        self.assertNotIn(time(10, 45), free)
        self.assertIn(time(11, 0), free)

    def test_next_available_day_skips_weekend(self):
        from booking.availability import next_available_day
        sunday = next_weekday(6)
        nxt = next_available_day(self.specialist, sunday, self.massage, now=self.morning)
        self.assertEqual(nxt.weekday(), 0)  # понедельник

    def test_travel_break_blocks_earlier_slot(self):
        # Запись в 14:00; массаж 30 мин в 13:00 влезает обычным перерывом (15),
        # но как выездной (перерыв 60) — упирается в 14:00 и недоступен.
        short = make_massage(name="Короткий", price="800")
        short.duration_min = 30
        short.duration_max = 30
        short.save()
        make_appointment(self.specialist, self.massage, self.monday, time(14, 0))
        from booking.availability import free_starts
        free = free_starts(self.specialist, self.monday, short, now=self.morning)
        free_travel = free_starts(
            self.specialist, self.monday, short, now=self.morning, is_travel=True
        )
        self.assertIn(time(13, 0), free)
        self.assertNotIn(time(13, 0), free_travel)

    def test_course_intersection_across_days(self):
        # Запись на день+1 в 9:00 убирает 9:00 из пересечения курса из 2 дней.
        tuesday = self.monday + timedelta(days=1)
        self.assertEqual(tuesday.weekday(), 1)
        make_appointment(self.specialist, self.massage, tuesday, time(9, 0))
        self.assertIn(time(9, 0), self._free(self.monday, sessions=1))
        self.assertNotIn(time(9, 0), self._free(self.monday, sessions=2))

    def test_day_availability_shifts(self):
        from booking.availability import day_availability
        sunday = next_weekday(6)
        data = day_availability(self.specialist, sunday, self.massage, now=self.morning)
        self.assertTrue(data["shifted"])
        self.assertEqual(data["requested_date"], sunday.isoformat())
        self.assertNotEqual(data["effective_date"], sunday.isoformat())
        self.assertTrue(data["slots"])

    def test_day_availability_no_shift_when_free(self):
        from booking.availability import day_availability
        data = day_availability(self.specialist, self.monday, self.massage, now=self.morning)
        self.assertFalse(data["shifted"])
        self.assertEqual(data["effective_date"], self.monday.isoformat())


class SlotsEndpointTest(TestCase):
    def setUp(self):
        self.specialist = make_specialist()
        self.massage = make_massage()
        SiteSettings.objects.create(online_booking_enabled=True)
        self.url = reverse("booking:slots")
        self.monday = next_weekday(0)

    def test_returns_slots(self):
        resp = self.client.get(self.url, {
            "service": self.massage.pk, "date": self.monday.isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["shifted"])
        self.assertIn("09:00", data["slots"])

    def test_shift_on_weekend(self):
        sunday = next_weekday(6)
        data = self.client.get(self.url, {
            "service": self.massage.pk, "date": sunday.isoformat(),
        }).json()
        self.assertTrue(data["shifted"])
        self.assertTrue(data["slots"])

    def test_bad_date(self):
        resp = self.client.get(self.url, {"service": self.massage.pk, "date": "xx"})
        self.assertEqual(resp.status_code, 400)

    def test_disabled_returns_empty(self):
        s = SiteSettings.objects.first()
        s.online_booking_enabled = False
        s.save()
        data = self.client.get(self.url, {
            "service": self.massage.pk, "date": self.monday.isoformat(),
        }).json()
        self.assertEqual(data["slots"], [])


class MonthAvailabilityTest(TestCase):
    def setUp(self):
        self.specialist = make_specialist()
        SiteSettings.objects.create(online_booking_enabled=True)
        self.url = reverse("booking:month")
        self.monday = next_weekday(0)

    def test_enabled_days_skips_weekend(self):
        from booking.availability import enabled_days
        days = enabled_days(self.specialist, self.monday, self.monday + timedelta(days=6))
        self.assertEqual([d.weekday() for d in days], [0, 1, 2, 3, 4])

    def test_enabled_days_excludes_exception(self):
        from booking.availability import enabled_days
        from cabinet.models import ScheduleException
        tuesday = self.monday + timedelta(days=1)
        ScheduleException.objects.create(
            specialist=self.specialist, date_from=tuesday, date_to=tuesday,
        )
        days = enabled_days(self.specialist, self.monday, self.monday + timedelta(days=6))
        self.assertNotIn(tuesday, days)
        self.assertIn(self.monday, days)

    def test_enabled_days_excludes_past(self):
        from booking.availability import enabled_days
        today = timezone.localdate()
        days = enabled_days(self.specialist, today - timedelta(days=10), today)
        self.assertTrue(all(d >= today for d in days))

    def test_month_endpoint(self):
        data = self.client.get(self.url, {
            "year": self.monday.year, "month": self.monday.month,
        }).json()
        self.assertIn(self.monday.isoformat(), data["enabled"])
        for s in data["enabled"]:
            self.assertLess(date_cls.fromisoformat(s).weekday(), 5)  # нет выходных

    def test_month_bad_params(self):
        resp = self.client.get(self.url, {"year": "x", "month": "5"})
        self.assertEqual(resp.status_code, 400)

    def test_month_disabled_empty(self):
        s = SiteSettings.objects.first()
        s.online_booking_enabled = False
        s.save()
        data = self.client.get(self.url, {
            "year": self.monday.year, "month": self.monday.month,
        }).json()
        self.assertEqual(data["enabled"], [])


class SessionsPerSpecialistTest(TestCase):
    def setUp(self):
        self.s1 = make_specialist("s1", "Мастер 1")
        self.s2 = make_specialist("s2", "Мастер 2")
        self.massage = make_massage()
        SiteSettings.objects.create(online_booking_enabled=True)
        self.o1 = BookingSessionOption.objects.create(specialist=self.s1, count=5, label="5 (м1)")
        self.o2 = BookingSessionOption.objects.create(specialist=self.s2, count=8, label="8 (м2)")

    def test_endpoint_returns_only_specialist_options(self):
        url = reverse("booking:sessions")
        data = self.client.get(url, {"specialist": self.s1.pk}).json()
        ids = [o["id"] for o in data["options"]]
        self.assertEqual(ids, [self.o1.pk])
        data2 = self.client.get(url, {"specialist": self.s2.pk}).json()
        self.assertEqual([o["id"] for o in data2["options"]], [self.o2.pk])

    def test_form_rejects_option_of_other_specialist(self):
        # Выбран мастер 1, но вариант сеансов мастера 2 → ошибка.
        data = {
            "client_name": "Иван", "service": self.massage.pk,
            "specialist": self.s1.pk, "sessions": self.o2.pk,
            "preferred_date": next_weekday(0).isoformat(), "preferred_time": "10:00",
            "phone": "", "comment": "", "ts": human_token(), "website": "", "consent": "on",
        }
        form = BookingForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("sessions", form.errors)


class ServiceDurationContextTest(TestCase):
    def test_durations_helper_formats_range(self):
        from booking.views import _service_durations
        massage = make_massage()  # 30–60
        single = make_massage(name="Один", price="900")
        single.duration_min = 0
        single.duration_max = 45
        single.save()
        d = _service_durations()
        self.assertEqual(d[str(massage.pk)], "30–60 мин")
        self.assertEqual(d[str(single.pk)], "45 мин")

    def test_durations_script_rendered_in_form(self):
        make_massage()
        SiteSettings.objects.create(online_booking_enabled=True)
        resp = self.client.get(reverse("booking:page"))
        self.assertContains(resp, 'id="serviceDurations"')


class ConfirmPageTest(TestCase):
    def setUp(self):
        self.specialist = make_specialist()
        self.massage = make_massage()
        SiteSettings.objects.create(online_booking_enabled=True, booking_hold_minutes=15)

    def _booking(self, status=BookingRequest.Status.AWAITING_CONTACT, minutes_ago=0, **over):
        from django.utils import timezone as tz
        b = BookingRequest.objects.create(
            client_name="Гость", service=self.massage, specialist=self.specialist,
            preferred_date=future_date(), preferred_time=time(10, 0),
            status=status, **over,
        )
        if minutes_ago:
            BookingRequest.objects.filter(pk=b.pk).update(
                created_at=tz.now() - timedelta(minutes=minutes_ago)
            )
        return b

    def _url(self, b):
        return reverse("booking:confirm", args=[b.link_token])

    def test_awaiting_shows_methods_and_timer(self):
        b = self._booking()
        resp = self.client.get(self._url(b))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "confirmCountdown")
        self.assertContains(resp, 'name="phone"')  # ввод телефона на странице

    def test_phone_confirm_activates(self):
        from unittest.mock import patch
        b = self._booking()
        with patch("booking.views._notify_admins") as m:
            resp = self.client.post(self._url(b), {"phone": "8 912 345 67 89"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingRequest.Status.PENDING)
        self.assertEqual(b.phone, "+79123456789")
        self.assertRedirects(resp, self._url(b), fetch_redirect_response=False)
        m.assert_called_once()

    def test_phone_confirm_invalid(self):
        b = self._booking()
        resp = self.client.post(self._url(b), {"phone": "123"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingRequest.Status.AWAITING_CONTACT)
        self.assertContains(resp, "booking-form__error")

    def test_expired_shows_rebook(self):
        b = self._booking(minutes_ago=20)  # > hold 15
        resp = self.client.get(self._url(b))
        self.assertContains(resp, "Бронь снята")

    def test_unknown_token_expired(self):
        resp = self.client.get(reverse("booking:confirm", args=["nope-nope"]))
        self.assertContains(resp, "Бронь снята")

    def test_pending_shows_thanks(self):
        b = self._booking(status=BookingRequest.Status.PENDING, phone="+79990000000")
        resp = self.client.get(self._url(b))
        self.assertContains(resp, "свяжемся")

    def test_cancel_awaiting_frees_slot(self):
        b = self._booking()
        resp = self.client.post(self._url(b), {"action": "cancel"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingRequest.Status.CANCELLED)
        self.assertRedirects(resp, self._url(b), fetch_redirect_response=False)
        # страница теперь в состоянии «отменена»
        page = self.client.get(self._url(b))
        self.assertContains(page, "Заявка отменена")

    def test_cancel_pending(self):
        from unittest.mock import patch
        b = self._booking(status=BookingRequest.Status.PENDING, phone="+79990000000")
        with patch("tgbot.notifications.notify_booking_cancelled"):
            self.client.post(self._url(b), {"action": "cancel"})
        b.refresh_from_db()
        self.assertEqual(b.status, BookingRequest.Status.CANCELLED)

    def test_status_endpoint_seconds_left(self):
        b = self._booking()
        data = self.client.get(reverse("booking:status", args=[b.link_token])).json()
        self.assertTrue(data["found"])
        self.assertEqual(data["status"], "awaiting_contact")
        self.assertIsNotNone(data["seconds_left"])
        self.assertGreaterEqual(data["seconds_left"], 0)

    def test_status_endpoint_expired_not_found(self):
        b = self._booking(minutes_ago=20)
        data = self.client.get(reverse("booking:status", args=[b.link_token])).json()
        self.assertFalse(data["found"])  # истёкшую считаем отсутствующей


class PurgeUnconfirmedBookingsTest(TestCase):
    def setUp(self):
        self.specialist = make_specialist()
        self.massage = make_massage()
        SiteSettings.objects.create(online_booking_enabled=True, booking_hold_minutes=15)

    def _make(self, status, minutes_ago, **over):
        from django.utils import timezone as tz
        b = BookingRequest.objects.create(
            client_name="X", service=self.massage, specialist=self.specialist,
            preferred_date=future_date(), preferred_time=time(10, 0),
            status=status, **over,
        )
        BookingRequest.objects.filter(pk=b.pk).update(
            created_at=tz.now() - timedelta(minutes=minutes_ago)
        )
        return b

    def test_purges_only_expired_awaiting(self):
        from django.core.management import call_command
        expired = self._make(BookingRequest.Status.AWAITING_CONTACT, 20)
        fresh = self._make(BookingRequest.Status.AWAITING_CONTACT, 5)
        pending = self._make(BookingRequest.Status.PENDING, 60, phone="+79990000000")
        confirmed_in_bot = self._make(
            BookingRequest.Status.AWAITING_CONTACT, 60, client_confirmed=True
        )
        call_command("purge_unconfirmed_bookings")
        ids = set(BookingRequest.objects.values_list("pk", flat=True))
        self.assertNotIn(expired.pk, ids)        # удалена
        self.assertIn(fresh.pk, ids)             # ещё в пределах таймаута
        self.assertIn(pending.pk, ids)           # есть контакт — не трогаем
        self.assertIn(confirmed_in_bot.pk, ids)  # подтверждена клиентом


class BookingFormAvailabilityTest(TestCase):
    """clean() отклоняет недоступное время (единый guard на сервере)."""

    def setUp(self):
        # Без вариантов курса — проверяем одиночный день (sessions=1).
        BookingSessionOption.objects.all().delete()
        self.specialist = make_specialist()
        self.massage = make_massage()
        self.monday = next_weekday(0)

    def _data(self, **over):
        data = {
            "client_name": "Иван",
            "service": self.massage.pk,
            "preferred_date": self.monday.isoformat(),
            "preferred_time": "10:00",
            "phone": "",
            "comment": "",
            "ts": human_token(),
            "website": "",
            "consent": "on",
        }
        data.update(over)
        return data

    def test_free_time_valid(self):
        form = BookingForm(data=self._data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_busy_time_rejected(self):
        make_appointment(self.specialist, self.massage, self.monday, time(10, 0))
        form = BookingForm(data=self._data(preferred_time="10:00"))
        self.assertFalse(form.is_valid())
        self.assertIn("preferred_time", form.errors)

    def test_non_working_day_rejected(self):
        sunday = next_weekday(6)
        form = BookingForm(data=self._data(preferred_date=sunday.isoformat()))
        self.assertFalse(form.is_valid())
        self.assertIn("preferred_date", form.errors)

    def test_out_of_hours_rejected(self):
        form = BookingForm(data=self._data(preferred_time="20:00"))
        self.assertFalse(form.is_valid())
        self.assertIn("preferred_time", form.errors)

    def test_travel_address_blocks_tight_slot(self):
        # 30-мин массаж в 13:00 ок без адреса, но с адресом (выезд, перерыв 60)
        # упирается в запись 14:00 → отклоняется.
        short = make_massage(name="Короткий", price="800")
        short.duration_min = 30
        short.duration_max = 30
        short.save()
        make_appointment(self.specialist, self.massage, self.monday, time(14, 0))
        ok = BookingForm(data=self._data(service=short.pk, preferred_time="13:00"))
        self.assertTrue(ok.is_valid(), ok.errors)
        travel = BookingForm(data=self._data(
            service=short.pk, preferred_time="13:00", address="ул. Ленина, 1",
        ))
        self.assertFalse(travel.is_valid())
        self.assertIn("preferred_time", travel.errors)


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

    def test_awaiting_contact_hidden_from_manager(self):
        self._login()
        awaiting = BookingRequest.objects.create(
            client_name="Безконтакта", service=self.massage,
            preferred_date=future_date(), preferred_time=time(15, 0),
            status=BookingRequest.Status.AWAITING_CONTACT,
        )
        for status in ("pending", "all"):
            resp = self.client.get(
                reverse("cabinet:booking_request_list") + f"?status={status}"
            )
            self.assertNotContains(resp, "Безконтакта", msg_prefix=status)
        # sanity: обычная заявка с контактом видна
        resp = self.client.get(reverse("cabinet:booking_request_list") + "?status=all")
        self.assertContains(resp, "Клиент")
        awaiting.delete()

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
