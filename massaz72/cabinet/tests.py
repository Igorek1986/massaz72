from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse

from services.models import Massage
from .forms import find_time_conflicts
from .models import (
    Appointment, AppointmentSeries, BlockedSlot, Discount,
    ScheduleException, Specialist, WorkSchedule,
)
from .views import _appointment_end_time, _next_series_working_day

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_massage(name="Массаж", duration=60, price=1000):
    return Massage.objects.create(
        name=name, price=price,
        duration_min=duration, duration_max=duration,
        massage_type="ADULT",
    )


def _make_specialist(username="specialist"):
    user = User.objects.create_user(username=username, password="pass")
    spec = Specialist.objects.create(user=user, name="Тест")
    WorkSchedule.objects.create(
        specialist=spec,
        monday=True, tuesday=True, wednesday=True,
        thursday=True, friday=True, saturday=False, sunday=False,
        break_between_minutes=15,
        break_between_travel_minutes=60,
    )
    return spec


def _make_apt(spec, apt_date, time_start, service=None, cost=1000, status="scheduled", parent=None, series=None):
    return Appointment.objects.create(
        specialist=spec,
        client_name="Клиент",
        date=apt_date,
        time_start=time_start,
        cost=cost,
        service=service,
        status=status,
        parent=parent,
        series=series,
    )


# ---------------------------------------------------------------------------
# find_time_conflicts
# ---------------------------------------------------------------------------

class FindTimeConflictsTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist()
        self.massage = _make_massage(duration=60)
        self.day = date(2026, 6, 10)

    def test_no_conflict_when_no_existing(self):
        conflicts = find_time_conflicts(
            self.day, time(10, 0), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        self.assertEqual(conflicts, [])

    def test_conflict_overlap(self):
        # Existing: 10:00–11:00 (60 min) + 15 min break
        _make_apt(self.spec, self.day, time(10, 0), service=self.massage)
        # New at 10:30 overlaps
        conflicts = find_time_conflicts(
            self.day, time(10, 30), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        self.assertEqual(len(conflicts), 1)

    def test_no_conflict_after_break(self):
        # Existing: 10:00–11:00, break 15 min → free from 11:15
        _make_apt(self.spec, self.day, time(10, 0), service=self.massage)
        conflicts = find_time_conflicts(
            self.day, time(11, 15), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        self.assertEqual(conflicts, [])

    def test_conflict_within_break_period(self):
        # New at 11:10 still within break window (end 11:00 + 15 = 11:15)
        _make_apt(self.spec, self.day, time(10, 0), service=self.massage)
        conflicts = find_time_conflicts(
            self.day, time(11, 10), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        self.assertEqual(len(conflicts), 1)

    def test_cancelled_not_counted(self):
        _make_apt(self.spec, self.day, time(10, 0), service=self.massage, status="cancelled")
        conflicts = find_time_conflicts(
            self.day, time(10, 0), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        self.assertEqual(conflicts, [])

    def test_exclude_pk(self):
        apt = _make_apt(self.spec, self.day, time(10, 0), service=self.massage)
        conflicts = find_time_conflicts(
            self.day, time(10, 0), self.massage, break_minutes=15,
            specialist=self.spec, exclude_pk=apt.pk,
        )
        self.assertEqual(conflicts, [])

    def test_children_excluded(self):
        # Parent at 10:00, child linked via parent FK
        parent = _make_apt(self.spec, self.day, time(10, 0), service=self.massage)
        _make_apt(self.spec, self.day, time(11, 0), service=self.massage, parent=parent)
        # Only parent should count; new slot at 11:10 conflicts with parent's break,
        # but since child is filtered out, we only see parent conflict
        conflicts = find_time_conflicts(
            self.day, time(10, 30), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        # Should find the parent, not the child
        self.assertEqual(len(conflicts), 1)
        self.assertIsNone(conflicts[0].parent_id)

    def test_existing_extra_duration_extends_conflict_window(self):
        # Existing parent 10:00 (60 min) + child 11:00 (30 min extra) + 15 break → free at 11:45
        apt = _make_apt(self.spec, self.day, time(10, 0), service=self.massage)
        extra_svc = _make_massage(name="Доп", duration=30)
        _make_apt(self.spec, self.day, time(11, 0), service=extra_svc, parent=apt)

        # 11:40 still in break window → conflict
        conflicts = find_time_conflicts(
            self.day, time(11, 40), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        self.assertEqual(len(conflicts), 1)

        # 11:45 exactly free
        conflicts_free = find_time_conflicts(
            self.day, time(11, 45), self.massage, break_minutes=15,
            specialist=self.spec,
        )
        self.assertEqual(conflicts_free, [])

    def test_new_apt_extra_duration_blocks_later_slot(self):
        # Existing apt at 11:30 (60 min)
        _make_apt(self.spec, self.day, time(11, 30), service=self.massage)

        # New at 10:00 without extra: ends 11:00 + 15 = 11:15 → no conflict with 11:30
        no_extra = find_time_conflicts(
            self.day, time(10, 0), self.massage, break_minutes=15,
            specialist=self.spec, extra_duration=0,
        )
        self.assertEqual(no_extra, [])

        # New at 10:00 with extra 30 min: ends 11:30 + 15 = 11:45 → overlaps 11:30
        with_extra = find_time_conflicts(
            self.day, time(10, 0), self.massage, break_minutes=15,
            specialist=self.spec, extra_duration=30,
        )
        self.assertEqual(len(with_extra), 1)


# ---------------------------------------------------------------------------
# _appointment_end_time
# ---------------------------------------------------------------------------

class AppointmentEndTimeTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("endtime_spec")
        self.day = date(2026, 6, 10)

    def test_main_service_only(self):
        massage = _make_massage("Спина", duration=60)
        apt = _make_apt(self.spec, self.day, time(10, 0), service=massage)
        self.assertEqual(_appointment_end_time(apt), time(11, 0))

    def test_includes_additional_services(self):
        massage = _make_massage("Спина", duration=60)
        extra = _make_massage("Шея", duration=30)
        apt = _make_apt(self.spec, self.day, time(10, 0), service=massage)
        _make_apt(self.spec, self.day, time(11, 0), service=extra, parent=apt)
        # 60 (main) + 30 (extra) = 90 min → 11:30
        self.assertEqual(_appointment_end_time(apt), time(11, 30))

    def test_no_service_returns_start(self):
        apt = _make_apt(self.spec, self.day, time(10, 0), service=None)
        self.assertEqual(_appointment_end_time(apt), time(10, 0))

    def test_uses_duration_max(self):
        massage = Massage.objects.create(
            name="Диапазон", price=1000,
            duration_min=30, duration_max=90, massage_type="ADULT",
        )
        apt = _make_apt(self.spec, self.day, time(10, 0), service=massage)
        # duration_max (90) → 11:30
        self.assertEqual(_appointment_end_time(apt), time(11, 30))

    def test_crosses_midnight(self):
        massage = _make_massage("Поздний", duration=90)
        apt = _make_apt(self.spec, self.day, time(23, 0), service=massage)
        # 23:00 + 90 min = 00:30 next day → time(0, 30)
        self.assertEqual(_appointment_end_time(apt), time(0, 30))


# ---------------------------------------------------------------------------
# _next_series_working_day
# ---------------------------------------------------------------------------

class NextSeriesWorkingDayTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist()
        self.massage = _make_massage()
        self.series = AppointmentSeries.objects.create(
            specialist=self.spec, service=self.massage, total_sessions=3
        )

    def test_next_day_when_friday(self):
        # Last appointment on Friday 2026-06-12 → next working day is Monday 2026-06-15
        fri = date(2026, 6, 12)  # Friday
        _make_apt(self.spec, fri, time(10, 0), service=self.massage, series=self.series)
        result = _next_series_working_day(self.series.pk, self.spec)
        self.assertEqual(result, date(2026, 6, 15))  # Monday

    def test_next_day_when_monday(self):
        mon = date(2026, 6, 9)  # Monday
        _make_apt(self.spec, mon, time(10, 0), service=self.massage, series=self.series)
        result = _next_series_working_day(self.series.pk, self.spec)
        self.assertEqual(result, date(2026, 6, 10))  # Tuesday

    def test_returns_none_when_no_appointments(self):
        result = _next_series_working_day(self.series.pk, self.spec)
        self.assertIsNone(result)

    def test_skips_saturday_sunday(self):
        # Last appointment Thursday 2026-06-11, schedule Mon–Fri
        thu = date(2026, 6, 11)  # Thursday
        _make_apt(self.spec, thu, time(10, 0), service=self.massage, series=self.series)
        # Friday is a working day
        result = _next_series_working_day(self.series.pk, self.spec)
        self.assertEqual(result, date(2026, 6, 12))  # Friday


# ---------------------------------------------------------------------------
# series_cancel_action (view)
# ---------------------------------------------------------------------------

class SeriesCancelActionTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("cancel_spec")
        self.massage = _make_massage("Спина", duration=60)
        self.extra_massage = _make_massage("Шея", duration=30)
        self.series = AppointmentSeries.objects.create(
            specialist=self.spec, service=self.massage, total_sessions=3
        )
        self.client.force_login(self.spec.user)

    def _url(self, pk):
        return reverse("cabinet:series_cancel_action", args=[pk])

    def _make_series_apts(self, count=3):
        """Create `count` parent appointments in the series."""
        apts = []
        for i in range(count):
            d = date(2026, 6, 9) + timedelta(days=i)
            apts.append(_make_apt(self.spec, d, time(10, 0), service=self.massage, series=self.series))
        return apts

    def test_cancel_one_include_main(self):
        apts = self._make_series_apts(3)
        r = self.client.post(self._url(apts[1].pk), {
            "action": "cancel_one", "include_main": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        self.assertFalse(Appointment.objects.filter(pk=apts[1].pk).exists())
        # Others unchanged
        self.assertTrue(Appointment.objects.filter(pk=apts[0].pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=apts[2].pk).exists())

    def test_cancel_following_include_main(self):
        apts = self._make_series_apts(3)
        r = self.client.post(self._url(apts[1].pk), {
            "action": "cancel_following", "include_main": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        self.assertTrue(Appointment.objects.filter(pk=apts[0].pk).exists())
        self.assertFalse(Appointment.objects.filter(pk=apts[1].pk).exists())
        self.assertFalse(Appointment.objects.filter(pk=apts[2].pk).exists())

    def test_cancel_one_extra_service_only(self):
        apts = self._make_series_apts(1)
        child = _make_apt(
            self.spec, apts[0].date, time(11, 0),
            service=self.extra_massage, parent=apts[0], series=self.series
        )
        r = self.client.post(self._url(apts[0].pk), {
            "action": "cancel_one",
            f"include_service_{self.extra_massage.pk}": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        # Main appointment stays
        self.assertTrue(Appointment.objects.filter(pk=apts[0].pk).exists())
        # Extra service removed
        self.assertFalse(Appointment.objects.filter(pk=child.pk).exists())

    def test_cancel_following_extra_service_only(self):
        # Two parent appointments each with an extra service
        apts = self._make_series_apts(2)
        children = []
        for apt in apts:
            c = _make_apt(
                self.spec, apt.date, time(11, 0),
                service=self.extra_massage, parent=apt, series=self.series
            )
            children.append(c)

        r = self.client.post(self._url(apts[0].pk), {
            "action": "cancel_following",
            f"include_service_{self.extra_massage.pk}": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        # Parent appointments stay
        self.assertTrue(Appointment.objects.filter(pk=apts[0].pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=apts[1].pk).exists())
        # Extra services removed from both (both ≥ apts[0].date)
        self.assertFalse(Appointment.objects.filter(pk=children[0].pk).exists())
        self.assertFalse(Appointment.objects.filter(pk=children[1].pk).exists())


# ---------------------------------------------------------------------------
# series_reschedule
# ---------------------------------------------------------------------------

class SeriesRescheduleTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("reschedule_spec")
        self.massage = _make_massage("Спина", duration=60)
        self.extra_massage = _make_massage("Шея", duration=30)
        self.series = AppointmentSeries.objects.create(
            specialist=self.spec, service=self.massage, total_sessions=3
        )
        self.client.force_login(self.spec.user)

    def _url(self, pk):
        return reverse("cabinet:series_reschedule", args=[pk])

    def _make_series_apts(self, dates):
        return [
            _make_apt(self.spec, d, time(10, 0), service=self.massage, series=self.series)
            for d in dates
        ]

    def test_reschedule_one_moves_only_selected(self):
        # 3 appointments: Tue Jun 9, Wed Jun 10, Thu Jun 11
        apts = self._make_series_apts([date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)])
        r = self.client.post(self._url(apts[1].pk), {
            "action": "reschedule_one",
            "target_date": "2026-06-22",
            "new_time": "10:00",
            "include_main": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        for apt in apts:
            apt.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 9))
        self.assertEqual(apts[1].date, date(2026, 6, 22))
        self.assertEqual(apts[2].date, date(2026, 6, 11))

    def test_reschedule_one_without_selection_moves_whole(self):
        # Без галочек (старый сценарий) — переносится запись целиком с доп. услугой
        apts = self._make_series_apts([date(2026, 6, 9)])
        child = _make_apt(
            self.spec, apts[0].date, time(11, 0),
            service=self.extra_massage, parent=apts[0], series=self.series,
        )
        r = self.client.post(self._url(apts[0].pk), {
            "target_date": "2026-06-22",
            "new_time": "",
        })
        self.assertIn(r.status_code, [200, 302])
        apts[0].refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 22))
        self.assertEqual(child.date, date(2026, 6, 22))
        self.assertEqual(child.parent_id, apts[0].pk)

    def test_reschedule_one_moves_children_with_main(self):
        apts = self._make_series_apts([date(2026, 6, 9)])
        child = _make_apt(
            self.spec, apts[0].date, time(11, 0),
            service=self.extra_massage, parent=apts[0], series=self.series,
        )
        r = self.client.post(self._url(apts[0].pk), {
            "action": "reschedule_one",
            "target_date": "2026-06-22",
            "new_time": "12:00",
            "include_main": "1",
            f"include_service_{self.extra_massage.pk}": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        apts[0].refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 22))
        self.assertEqual(apts[0].time_start, time(12, 0))
        self.assertEqual(child.date, date(2026, 6, 22))
        self.assertEqual(child.time_start, time(13, 0))  # после основного (60 мин)
        self.assertEqual(child.parent_id, apts[0].pk)

    def test_reschedule_one_child_only(self):
        apts = self._make_series_apts([date(2026, 6, 9)])
        child = _make_apt(
            self.spec, apts[0].date, time(11, 0),
            service=self.extra_massage, parent=apts[0], series=self.series,
        )
        r = self.client.post(self._url(apts[0].pk), {
            "action": "reschedule_one",
            "target_date": "2026-06-22",
            "new_time": "10:00",
            f"include_service_{self.extra_massage.pk}": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        apts[0].refresh_from_db()
        child.refresh_from_db()
        # Основная остаётся на месте
        self.assertEqual(apts[0].date, date(2026, 6, 9))
        # Доп. услуга отвязана и перенесена
        self.assertIsNone(child.parent_id)
        self.assertEqual(child.date, date(2026, 6, 22))
        self.assertEqual(child.time_start, time(10, 0))

    def test_reschedule_one_main_only_detaches_child(self):
        apts = self._make_series_apts([date(2026, 6, 9)])
        child = _make_apt(
            self.spec, apts[0].date, time(11, 0),
            service=self.extra_massage, parent=apts[0], series=self.series,
        )
        r = self.client.post(self._url(apts[0].pk), {
            "action": "reschedule_one",
            "target_date": "2026-06-22",
            "new_time": "10:00",
            "include_main": "1",
        })
        self.assertIn(r.status_code, [200, 302])
        apts[0].refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 22))
        # Доп. услуга осталась на прежней дате отдельной записью
        self.assertIsNone(child.parent_id)
        self.assertEqual(child.date, date(2026, 6, 9))
        self.assertEqual(child.time_start, time(11, 0))

    def test_reschedule_following_reflows_over_working_days(self):
        # Tue Jun 9, Wed Jun 10, Thu Jun 11 → с пятницы Jun 12: Fri 12, Mon 15, Tue 16
        apts = self._make_series_apts([date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)])
        r = self.client.post(self._url(apts[0].pk), {
            "action": "reschedule_following",
            "target_date": "2026-06-12",
            "new_time": "10:00",
        })
        self.assertIn(r.status_code, [200, 302])
        for apt in apts:
            apt.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 12))
        self.assertEqual(apts[1].date, date(2026, 6, 15))
        self.assertEqual(apts[2].date, date(2026, 6, 16))

    def test_reschedule_following_from_middle_keeps_earlier(self):
        apts = self._make_series_apts([date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)])
        r = self.client.post(self._url(apts[1].pk), {
            "action": "reschedule_following",
            "target_date": "2026-06-15",
            "new_time": "10:00",
        })
        self.assertIn(r.status_code, [200, 302])
        for apt in apts:
            apt.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 9))
        self.assertEqual(apts[1].date, date(2026, 6, 15))
        self.assertEqual(apts[2].date, date(2026, 6, 16))

    def test_reschedule_following_no_self_conflict(self):
        # Перенос на даты, пересекающиеся со старыми датами серии, не должен
        # конфликтовать с собственными записями серии
        apts = self._make_series_apts([date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)])
        r = self.client.post(self._url(apts[0].pk), {
            "action": "reschedule_following",
            "target_date": "2026-06-10",
            "new_time": "10:00",
        })
        self.assertIn(r.status_code, [200, 302])
        for apt in apts:
            apt.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 10))
        self.assertEqual(apts[1].date, date(2026, 6, 11))
        self.assertEqual(apts[2].date, date(2026, 6, 12))

    def test_reschedule_following_moves_children(self):
        apts = self._make_series_apts([date(2026, 6, 9), date(2026, 6, 10)])
        children = [
            _make_apt(self.spec, apt.date, time(11, 0),
                      service=self.extra_massage, parent=apt, series=self.series)
            for apt in apts
        ]
        r = self.client.post(self._url(apts[0].pk), {
            "action": "reschedule_following",
            "target_date": "2026-06-15",
            "new_time": "10:00",
        })
        self.assertIn(r.status_code, [200, 302])
        for obj in apts + children:
            obj.refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 15))
        self.assertEqual(apts[1].date, date(2026, 6, 16))
        self.assertEqual(children[0].date, date(2026, 6, 15))
        self.assertEqual(children[1].date, date(2026, 6, 16))
        self.assertEqual(children[0].time_start, time(11, 0))

    def test_reschedule_one_conflict_rerenders_form(self):
        apts = self._make_series_apts([date(2026, 6, 9)])
        # Чужая запись на целевой дате в то же время
        _make_apt(self.spec, date(2026, 6, 22), time(10, 0), service=self.massage)
        r = self.client.post(self._url(apts[0].pk), {
            "action": "reschedule_one",
            "target_date": "2026-06-22",
            "new_time": "10:00",
            "include_main": "1",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "form-error")
        apts[0].refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 9))

    def test_get_renders_form_with_default_target(self):
        # Последняя запись в пятницу Jun 12 → дефолтная дата переноса: понедельник Jun 15
        apts = self._make_series_apts([date(2026, 6, 11), date(2026, 6, 12)])
        r = self.client.get(self._url(apts[0].pk))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "2026-06-15")


# ---------------------------------------------------------------------------
# discount_confirm_delete / discount_delete
# ---------------------------------------------------------------------------

class DiscountDeleteTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("discount_spec")
        self.discount = Discount.objects.create(
            discount_type="percentage", value=15,
            date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
        )
        self.client.force_login(self.spec.user)

    def test_confirm_renders_custom_modal(self):
        r = self.client.get(reverse("cabinet:discount_confirm_delete", args=[self.discount.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Удалить скидку?")
        # Кнопка подтверждения постит на discount_delete — модалка в нашем стиле
        self.assertContains(r, reverse("cabinet:discount_delete", args=[self.discount.pk]))
        self.assertContains(r, "apt-form--confirm")
        # Скидка ещё на месте — GET ничего не удаляет
        self.assertTrue(Discount.objects.filter(pk=self.discount.pk).exists())

    def test_delete_removes_discount_and_closes_modal(self):
        r = self.client.post(reverse("cabinet:discount_delete", args=[self.discount.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Discount.objects.filter(pk=self.discount.pk).exists())
        # OOB-закрытие модалки + ретаргет секции скидок
        self.assertEqual(r["HX-Retarget"], "#discounts-section")
        self.assertIn('id="cabinet-modal"', r.content.decode())

    def test_confirm_requires_manage_prices(self):
        self.spec.can_manage_prices = False
        self.spec.save(update_fields=["can_manage_prices"])
        r = self.client.get(reverse("cabinet:discount_confirm_delete", args=[self.discount.pk]))
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# Settings: confirm-delete modals in our style (blocked slot / exception)
# ---------------------------------------------------------------------------

class SettingsConfirmDeleteTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("settings_spec")
        self.client.force_login(self.spec.user)

    def test_blocked_slot_confirm_then_delete(self):
        slot = BlockedSlot.objects.create(
            specialist=self.spec, date=date(2026, 6, 10),
            time_start=time(10, 0), time_end=time(11, 0),
        )
        r = self.client.get(reverse("cabinet:blocked_slot_confirm_delete", args=[slot.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Удалить заблокированное время?")
        self.assertContains(r, "apt-form--confirm")
        self.assertTrue(BlockedSlot.objects.filter(pk=slot.pk).exists())

        r = self.client.post(reverse("cabinet:blocked_slot_delete", args=[slot.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(BlockedSlot.objects.filter(pk=slot.pk).exists())
        self.assertEqual(r["HX-Retarget"], "#blocked-slots-section")
        self.assertIn('id="cabinet-modal"', r.content.decode())

    def test_exception_confirm_then_delete(self):
        exc = ScheduleException.objects.create(
            specialist=self.spec, date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 12), exception_type=ScheduleException.DAY_OFF,
        )
        r = self.client.get(reverse("cabinet:exception_confirm_delete", args=[exc.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Удалить исключение?")
        self.assertContains(r, "apt-form--confirm")
        self.assertTrue(ScheduleException.objects.filter(pk=exc.pk).exists())

        r = self.client.post(reverse("cabinet:exception_delete", args=[exc.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ScheduleException.objects.filter(pk=exc.pk).exists())
        self.assertEqual(r["HX-Retarget"], "#exceptions-section")
        self.assertIn('id="cabinet-modal"', r.content.decode())


# ---------------------------------------------------------------------------
# Prices: apply-change confirm modal
# ---------------------------------------------------------------------------

class PricesApplyConfirmTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("apply_spec")
        self.client.force_login(self.spec.user)

    def test_confirm_renders_modal_without_applying(self):
        m = _make_massage("Спина", duration=60, price=1000)
        m.new_price = 1200
        m.save(update_fields=["new_price"])
        r = self.client.get(reverse("cabinet:prices_confirm_apply"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Применить новые цены?")
        self.assertContains(r, "apt-form--confirm")
        # цена пока не изменилась — GET ничего не применяет
        m.refresh_from_db()
        self.assertEqual(m.price, 1000)

    def test_confirm_requires_manage_prices(self):
        self.spec.can_manage_prices = False
        self.spec.save(update_fields=["can_manage_prices"])
        r = self.client.get(reverse("cabinet:prices_confirm_apply"))
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# Security: prices reject negative values (save bypasses Model.clean)
# ---------------------------------------------------------------------------

class PriceNegativeRejectTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("price_neg_spec")
        self.client.force_login(self.spec.user)
        self.massage = _make_massage("Спина", duration=60, price=1000)

    def test_save_current_ignores_negative_price(self):
        r = self.client.post(reverse("cabinet:prices_save_current"), {
            f"price_{self.massage.pk}": "-500",
        })
        self.assertEqual(r.status_code, 200)
        self.massage.refresh_from_db()
        self.assertEqual(self.massage.price, Decimal("1000"))

    def test_save_current_accepts_valid_price(self):
        r = self.client.post(reverse("cabinet:prices_save_current"), {
            f"price_{self.massage.pk}": "1500",
        })
        self.assertEqual(r.status_code, 200)
        self.massage.refresh_from_db()
        self.assertEqual(self.massage.price, Decimal("1500"))

    def test_save_change_ignores_negative_new_price(self):
        from main.models import SiteSettings
        SiteSettings.objects.create()
        r = self.client.post(reverse("cabinet:prices_save_change"), {
            "price_change_date": "",
            f"new_price_{self.massage.pk}": "-200",
        })
        self.assertEqual(r.status_code, 200)
        self.massage.refresh_from_db()
        self.assertIsNone(self.massage.new_price)


# ---------------------------------------------------------------------------
# Security: appointment form escapes service names (no script breakout)
# ---------------------------------------------------------------------------

class AppointmentFormXSSTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("xss_spec")
        self.client.force_login(self.spec.user)

    def test_service_name_with_script_tag_is_escaped(self):
        _make_massage('</script><img src=x onerror=alert(1)>', duration=60, price=1000)
        r = self.client.get(reverse("cabinet:appointment_add"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        # Полезная нагрузка должна быть экранирована json_script, а не вставлена сырой
        self.assertNotIn("</script><img src=x", body)
        self.assertIn("apt-available-services", body)


# ---------------------------------------------------------------------------
# Security: archived massages are not reachable via public detail page
# ---------------------------------------------------------------------------

class ArchivedMassageDetailTest(TestCase):
    def test_archived_massage_returns_404(self):
        m = _make_massage("Архивный", duration=60, price=1000)
        m.slug = "arhivnyy"
        m.is_archived = True
        m.save(update_fields=["slug", "is_archived"])
        r = self.client.get(reverse("services:massage_detail", args=[m.slug]))
        self.assertEqual(r.status_code, 404)

    def test_active_massage_is_reachable(self):
        m = _make_massage("Активный", duration=60, price=1000)
        m.slug = "aktivnyy"
        m.save(update_fields=["slug"])
        r = self.client.get(reverse("services:massage_detail", args=[m.slug]))
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Security: login brute-force protection (django-axes)
# ---------------------------------------------------------------------------

class LoginBruteForceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="brute", password="rightpass")
        self.url = reverse("cabinet:login")

    def tearDown(self):
        from axes.utils import reset
        reset()

    def test_lockout_after_failed_attempts(self):
        for _ in range(5):
            self.client.post(self.url, {"username": "brute", "password": "wrong"})
        r = self.client.post(self.url, {"username": "brute", "password": "wrong"})
        self.assertEqual(r.status_code, 429)

    def test_lockout_blocks_even_correct_password(self):
        for _ in range(5):
            self.client.post(self.url, {"username": "brute", "password": "wrong"})
        r = self.client.post(self.url, {"username": "brute", "password": "rightpass"})
        self.assertEqual(r.status_code, 429)

    def test_valid_login_succeeds_below_limit(self):
        self.client.post(self.url, {"username": "brute", "password": "wrong"})
        r = self.client.post(self.url, {"username": "brute", "password": "rightpass"})
        self.assertEqual(r.status_code, 302)


# ---------------------------------------------------------------------------
# Security: access control (login, specialist, cross-specialist isolation)
# ---------------------------------------------------------------------------

class CabinetAccessControlTest(TestCase):
    def setUp(self):
        self.spec_a = _make_specialist("spec_a")
        self.spec_b = _make_specialist("spec_b")
        self.massage = _make_massage("Спина", duration=60, price=1000)
        self.apt_a = _make_apt(self.spec_a, date(2026, 6, 10), time(10, 0), service=self.massage)

    def test_anonymous_redirected_to_login(self):
        for url in [
            reverse("cabinet:index"),
            reverse("cabinet:prices"),
            reverse("cabinet:settings"),
            reverse("cabinet:day_schedule", args=["2026-06-10"]),
            reverse("cabinet:calendar_events"),
            reverse("cabinet:appointment_add"),
            reverse("cabinet:appointment_edit", args=[self.apt_a.pk]),
        ]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/cabinet/login/", r["Location"], url)

    def test_user_without_specialist_redirected_to_admin(self):
        user = User.objects.create_user(username="nospec", password="pass")
        self.client.force_login(user)
        r = self.client.get(reverse("cabinet:index"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("admin:index"))

    def test_other_specialist_cannot_open_edit_form(self):
        self.client.force_login(self.spec_b.user)
        r = self.client.get(reverse("cabinet:appointment_edit", args=[self.apt_a.pk]))
        self.assertEqual(r.status_code, 404)

    def test_other_specialist_cannot_change_status(self):
        self.client.force_login(self.spec_b.user)
        r = self.client.post(
            reverse("cabinet:appointment_status", args=[self.apt_a.pk]),
            {"status": Appointment.COMPLETED},
        )
        self.assertEqual(r.status_code, 404)
        self.apt_a.refresh_from_db()
        self.assertEqual(self.apt_a.status, Appointment.SCHEDULED)

    def test_other_specialist_cannot_delete(self):
        self.client.force_login(self.spec_b.user)
        r = self.client.post(reverse("cabinet:appointment_delete", args=[self.apt_a.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Appointment.objects.filter(pk=self.apt_a.pk).exists())

    def test_other_specialist_cannot_reschedule(self):
        self.client.force_login(self.spec_b.user)
        r = self.client.get(reverse("cabinet:series_reschedule", args=[self.apt_a.pk]))
        self.assertEqual(r.status_code, 404)

    def test_other_specialist_cannot_touch_settings_objects(self):
        exc = ScheduleException.objects.create(
            specialist=self.spec_a, date_from=date(2026, 7, 1), date_to=date(2026, 7, 2),
        )
        slot = BlockedSlot.objects.create(
            specialist=self.spec_a, date=date(2026, 7, 1),
            time_start=time(10, 0), time_end=time(11, 0),
        )
        self.client.force_login(self.spec_b.user)
        r = self.client.post(reverse("cabinet:exception_delete", args=[exc.pk]))
        self.assertEqual(r.status_code, 404)
        r = self.client.post(reverse("cabinet:blocked_slot_delete", args=[slot.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(ScheduleException.objects.filter(pk=exc.pk).exists())
        self.assertTrue(BlockedSlot.objects.filter(pk=slot.pk).exists())

    def test_day_schedule_hides_other_specialists_appointments(self):
        self.client.force_login(self.spec_b.user)
        r = self.client.get(reverse("cabinet:day_schedule", args=["2026-06-10"]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Клиент")


# ---------------------------------------------------------------------------
# Security: CSRF is enforced on cabinet POST endpoints
# ---------------------------------------------------------------------------

class CabinetCSRFTest(TestCase):
    def test_post_without_csrf_token_rejected(self):
        spec = _make_specialist("csrf_spec")
        apt = _make_apt(spec, date(2026, 6, 10), time(10, 0))
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(spec.user)
        r = client.post(reverse("cabinet:appointment_delete", args=[apt.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Appointment.objects.filter(pk=apt.pk).exists())


# ---------------------------------------------------------------------------
# Security: calendar_events rejects unbounded date ranges (DoS)
# ---------------------------------------------------------------------------

class CalendarEventsTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("cal_spec")
        self.client.force_login(self.spec.user)
        self.url = reverse("cabinet:calendar_events")

    def test_normal_range_returns_events(self):
        # 2026-06-13/14 — суббота и воскресенье (нерабочие в _make_specialist)
        _make_apt(self.spec, date(2026, 6, 10), time(10, 0))
        r = self.client.get(self.url, {"start": "2026-06-08", "end": "2026-06-15"})
        self.assertEqual(r.status_code, 200)
        events = r.json()
        day_off = [e for e in events if "fc-day-off" in e.get("classNames", [])]
        counts = [e for e in events if "fc-apt-count" in e.get("classNames", [])]
        self.assertEqual(len(day_off), 2)
        self.assertEqual(len(counts), 1)
        self.assertEqual(counts[0]["start"], "2026-06-10")

    def test_schedule_exception_marked_as_day_off(self):
        ScheduleException.objects.create(
            specialist=self.spec, date_from=date(2026, 6, 9), date_to=date(2026, 6, 9),
        )
        r = self.client.get(self.url, {"start": "2026-06-08", "end": "2026-06-13"})
        day_off = [e for e in r.json() if "fc-day-off" in e.get("classNames", [])]
        self.assertEqual([e["start"] for e in day_off], ["2026-06-09"])

    def test_huge_range_returns_empty(self):
        r = self.client.get(self.url, {"start": "2020-01-01", "end": "9999-12-31"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_reversed_range_returns_empty(self):
        r = self.client.get(self.url, {"start": "2026-06-15", "end": "2026-06-08"})
        self.assertEqual(r.json(), [])

    def test_invalid_params_return_empty(self):
        r = self.client.get(self.url, {"start": "garbage", "end": "also-garbage"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_max_allowed_range_still_works(self):
        r = self.client.get(self.url, {"start": "2026-01-01", "end": "2026-12-31"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.json()) > 0)  # выходные дни года размечены


# ---------------------------------------------------------------------------
# Security: prices endpoints require can_manage_prices
# ---------------------------------------------------------------------------

class PricesManagerPermissionTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("no_prices_spec")
        self.spec.can_manage_prices = False
        self.spec.save(update_fields=["can_manage_prices"])
        self.client.force_login(self.spec.user)
        self.massage = _make_massage("Спина", duration=60, price=1000)

    def test_post_endpoints_forbidden(self):
        for name, args, data in [
            ("cabinet:prices_save_current", [], {f"price_{self.massage.pk}": "1"}),
            ("cabinet:prices_save_change", [], {f"new_price_{self.massage.pk}": "1"}),
            ("cabinet:prices_apply_change", [], {}),
            ("cabinet:discount_delete", [1], {}),
            ("cabinet:massage_toggle_archive", [self.massage.pk], {}),
        ]:
            r = self.client.post(reverse(name, args=args), data)
            self.assertEqual(r.status_code, 403, name)
        self.massage.refresh_from_db()
        self.assertEqual(self.massage.price, Decimal("1000"))
        self.assertFalse(self.massage.is_archived)

    def test_form_endpoints_forbidden(self):
        for name, args in [
            ("cabinet:discount_add", []),
            ("cabinet:massage_add", []),
            ("cabinet:massage_edit", [self.massage.pk]),
        ]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 403, name)

    def test_prices_page_still_viewable(self):
        r = self.client.get(reverse("cabinet:prices"))
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Security: extra_pk in appointment edit cannot touch foreign children
# ---------------------------------------------------------------------------

class ExtraServicePkInjectionTest(TestCase):
    def setUp(self):
        self.spec_a = _make_specialist("inj_a")
        self.spec_b = _make_specialist("inj_b")
        self.massage = _make_massage("Спина", duration=60, price=1000)
        self.extra = _make_massage("Шея", duration=30, price=500)
        # Запись специалиста B с доп. услугой
        self.apt_b = _make_apt(self.spec_b, date(2026, 6, 10), time(10, 0), service=self.massage)
        self.child_b = _make_apt(
            self.spec_b, date(2026, 6, 10), time(11, 0),
            service=self.extra, cost=500, parent=self.apt_b,
        )
        # Запись специалиста A
        self.apt_a = _make_apt(self.spec_a, date(2026, 6, 10), time(14, 0), service=self.massage)

    def test_foreign_extra_pk_does_not_modify_other_child(self):
        self.client.force_login(self.spec_a.user)
        r = self.client.post(
            reverse("cabinet:appointment_edit", args=[self.apt_a.pk]),
            {
                "client_name": "Клиент",
                "date": "2026-06-10",
                "time_start": "14:00",
                "cost": "1000",
                "service": str(self.massage.pk),
                # Пытаемся «отредактировать» чужого ребёнка по его pk
                "extra_pk_0": str(self.child_b.pk),
                "extra_service_0": str(self.extra.pk),
                "extra_cost_0": "1",
            },
        )
        self.assertEqual(r.status_code, 200)
        # Чужая дочерняя запись не изменилась и осталась у своего родителя
        self.child_b.refresh_from_db()
        self.assertEqual(self.child_b.parent_id, self.apt_b.pk)
        self.assertEqual(self.child_b.cost, Decimal("500"))
        # У записи A появилась своя новая доп. услуга
        children_a = list(self.apt_a.additional_services.all())
        self.assertEqual(len(children_a), 1)
        self.assertEqual(children_a[0].cost, Decimal("1"))
