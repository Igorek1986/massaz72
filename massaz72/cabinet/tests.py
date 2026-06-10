from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse

from services.models import Massage
from .forms import find_time_conflicts
from .models import Appointment, AppointmentSeries, Specialist, WorkSchedule
from .views import _next_series_working_day

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
# series_reschedule — date shift
# ---------------------------------------------------------------------------

class SeriesRescheduleTest(TestCase):
    def setUp(self):
        self.spec = _make_specialist("reschedule_spec")
        self.massage = _make_massage("Спина", duration=60)
        self.series = AppointmentSeries.objects.create(
            specialist=self.spec, service=self.massage, total_sessions=3
        )
        self.client.force_login(self.spec.user)

    def _url(self, pk):
        return reverse("cabinet:series_reschedule", args=[pk])

    def test_shift_moves_all_following(self):
        # 3 appointments: Jun 9, 10, 11
        dates = [date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)]
        apts = [_make_apt(self.spec, d, time(10, 0), service=self.massage, series=self.series) for d in dates]

        # Reschedule from Jun 10 (apts[1]) → target Jun 12 (shift +2)
        r = self.client.post(self._url(apts[1].pk), {
            "target_date": "2026-06-12",
            "new_time": "",
        })
        self.assertIn(r.status_code, [200, 302])
        # apts[0] unchanged
        apts[0].refresh_from_db()
        self.assertEqual(apts[0].date, date(2026, 6, 9))
        # apts[1] → Jun 12
        apts[1].refresh_from_db()
        self.assertEqual(apts[1].date, date(2026, 6, 12))
        # apts[2] → Jun 13 (+2 from Jun 11)
        apts[2].refresh_from_db()
        self.assertEqual(apts[2].date, date(2026, 6, 13))
