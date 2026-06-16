from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cabinet.models import Specialist
from main.models import SiteSettings
from reviews.forms import ReviewForm
from reviews.models import Review
from reviews.spam import (
    MAX_FORM_AGE_SECONDS, MIN_FILL_SECONDS, THROTTLE_LIMIT,
    is_rate_limited, make_timestamp_token, timing_is_human,
)

User = get_user_model()


def _human_token(seconds_ago: int = MIN_FILL_SECONDS + 1) -> str:
    """Валидный time-trap токен, выписанный seconds_ago секунд назад."""
    from django.core import signing
    signer = signing.Signer(salt="reviews.timing")
    issued = int(timezone.now().timestamp()) - seconds_ago
    return signer.sign(str(issued))


class ReviewModelTest(TestCase):
    def test_public_excludes_pending_rejected_archived(self):
        approved = Review.objects.create(name="A", rating=5, text="ok",
                                         status=Review.Status.APPROVED)
        Review.objects.create(name="B", rating=4, text="pending",
                              status=Review.Status.PENDING)
        Review.objects.create(name="C", rating=1, text="rejected",
                              status=Review.Status.REJECTED)
        Review.objects.create(name="D", rating=5, text="archived",
                              status=Review.Status.APPROVED, is_archived=True)
        public = list(Review.objects.public())
        self.assertEqual(public, [approved])

    def test_default_status_pending(self):
        r = Review.objects.create(name="X", rating=3, text="t")
        self.assertEqual(r.status, Review.Status.PENDING)


class SpamHelpersTest(TestCase):
    def test_timing_rejects_missing_and_invalid(self):
        self.assertFalse(timing_is_human(""))
        self.assertFalse(timing_is_human("garbage"))

    def test_timing_rejects_too_fast(self):
        self.assertFalse(timing_is_human(_human_token(seconds_ago=1)))

    def test_timing_rejects_stale(self):
        self.assertFalse(timing_is_human(_human_token(seconds_ago=MAX_FORM_AGE_SECONDS + 10)))

    def test_timing_accepts_human(self):
        self.assertTrue(timing_is_human(_human_token()))

    def test_make_token_roundtrip_is_human(self):
        # Свежий токен слишком "быстрый" — сразу не проходит.
        self.assertFalse(timing_is_human(make_timestamp_token()))

    def test_rate_limit_counts_recent_only(self):
        self.assertFalse(is_rate_limited("1.2.3.4"))
        for _ in range(THROTTLE_LIMIT):
            Review.objects.create(name="N", rating=5, text="t", ip_address="1.2.3.4")
        self.assertTrue(is_rate_limited("1.2.3.4"))
        # Старые отзывы (вне окна) не считаются.
        old = Review.objects.create(name="O", rating=5, text="t", ip_address="9.9.9.9")
        Review.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        self.assertFalse(is_rate_limited("9.9.9.9"))

    def test_rate_limit_none_ip(self):
        self.assertFalse(is_rate_limited(None))


class ReviewFormTest(TestCase):
    def test_blank_name_and_text_invalid(self):
        form = ReviewForm(data={"name": "  ", "text": "  ", "rating": 5,
                                "ts": _human_token()})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("text", form.errors)

    def test_rating_out_of_range_invalid(self):
        form = ReviewForm(data={"name": "Ann", "text": "good", "rating": 9,
                                "ts": _human_token()})
        self.assertFalse(form.is_valid())
        self.assertIn("rating", form.errors)

    def test_valid_form(self):
        form = ReviewForm(data={"name": "Ann", "text": "good", "rating": 5,
                                "ts": _human_token()})
        self.assertTrue(form.is_valid())

    def test_unbound_form_has_ts_token(self):
        form = ReviewForm()
        self.assertTrue(form.fields["ts"].initial)


class ReviewCreateViewTest(TestCase):
    def setUp(self):
        self.url = reverse("reviews:create")
        self.settings_obj = SiteSettings.objects.create(reviews_enabled=True)

    def _post(self, **overrides):
        data = {
            "name": "Иван",
            "text": "Отличный массаж",
            "rating": "5",
            "ts": _human_token(),
            "website": "",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_happy_path_creates_pending(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("review=ok", resp["Location"])
        review = Review.objects.get()
        self.assertEqual(review.status, Review.Status.PENDING)
        self.assertEqual(review.name, "Иван")
        self.assertIsNotNone(review.ip_address)

    def test_honeypot_silently_drops(self):
        resp = self._post(website="http://spam")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("review=ok", resp["Location"])
        self.assertEqual(Review.objects.count(), 0)

    def test_timetrap_too_fast_silently_drops(self):
        resp = self._post(ts=_human_token(seconds_ago=0))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("review=ok", resp["Location"])
        self.assertEqual(Review.objects.count(), 0)

    def test_timetrap_missing_token_silently_drops(self):
        resp = self._post(ts="")
        self.assertEqual(Review.objects.count(), 0)

    def test_throttled_after_limit(self):
        for _ in range(THROTTLE_LIMIT):
            Review.objects.create(name="N", rating=5, text="t",
                                  ip_address="127.0.0.1")
        resp = self._post()
        self.assertIn("review=throttled", resp["Location"])
        self.assertEqual(Review.objects.filter(name="Иван").count(), 0)

    def test_invalid_form_rerenders_index(self):
        # Пустой текст не сохраняется, главная перерисовывается с формой,
        # ранее введённое имя сохраняется, показана ошибка поля.
        resp = self._post(text="   ")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Review.objects.count(), 0)
        self.assertContains(resp, 'class="review-form__error"')
        self.assertContains(resp, 'value="Иван"')

    def test_disabled_rejects_post(self):
        self.settings_obj.reviews_enabled = False
        self.settings_obj.save()
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Review.objects.count(), 0)

    def test_get_not_allowed(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


class HomePageReviewsTest(TestCase):
    def setUp(self):
        self.url = reverse("main:index")

    def test_section_hidden_when_disabled(self):
        SiteSettings.objects.create(reviews_enabled=False)
        Review.objects.create(name="A", rating=5, text="ok",
                              status=Review.Status.APPROVED)
        resp = self.client.get(self.url)
        self.assertNotContains(resp, 'id="reviews"')

    def test_section_shows_only_approved(self):
        SiteSettings.objects.create(reviews_enabled=True)
        Review.objects.create(name="Visible", rating=5, text="approved one",
                              status=Review.Status.APPROVED)
        Review.objects.create(name="Hidden", rating=2, text="pending one",
                              status=Review.Status.PENDING)
        resp = self.client.get(self.url)
        self.assertContains(resp, 'id="reviews"')
        self.assertContains(resp, "Visible")
        self.assertNotContains(resp, "Hidden")


class CabinetReviewsTest(TestCase):
    def setUp(self):
        self.super = User.objects.create_user("boss", password="pw", is_superuser=True)
        Specialist.objects.create(user=self.super, name="Босс")
        self.plain = User.objects.create_user("plain", password="pw")
        Specialist.objects.create(user=self.plain, name="Просто")
        self.settings_obj = SiteSettings.objects.create(reviews_enabled=False)
        self.review = Review.objects.create(name="Клиент", rating=4, text="норм",
                                            status=Review.Status.PENDING)

    def test_non_superuser_forbidden(self):
        self.client.force_login(self.plain)
        resp = self.client.get(reverse("cabinet:reviews"))
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("cabinet:reviews"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_superuser_can_open(self):
        self.client.force_login(self.super)
        resp = self.client.get(reverse("cabinet:reviews"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Клиент")

    def test_approve(self):
        self.client.force_login(self.super)
        resp = self.client.post(
            reverse("cabinet:review_approve", args=[self.review.pk]),
            {"status": "pending"},
        )
        self.assertEqual(resp.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.APPROVED)

    def test_reject(self):
        self.client.force_login(self.super)
        self.client.post(reverse("cabinet:review_reject", args=[self.review.pk]),
                         {"status": "pending"})
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.REJECTED)

    def test_archive_and_unarchive(self):
        self.client.force_login(self.super)
        self.client.post(reverse("cabinet:review_archive", args=[self.review.pk]),
                         {"status": "pending"})
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_archived)
        self.client.post(reverse("cabinet:review_unarchive", args=[self.review.pk]),
                         {"status": "archived"})
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_archived)

    def test_toggle_flips_setting(self):
        self.client.force_login(self.super)
        resp = self.client.post(reverse("cabinet:reviews_toggle"))
        self.assertEqual(resp.status_code, 200)
        self.settings_obj.refresh_from_db()
        self.assertTrue(self.settings_obj.reviews_enabled)
        self.client.post(reverse("cabinet:reviews_toggle"))
        self.settings_obj.refresh_from_db()
        self.assertFalse(self.settings_obj.reviews_enabled)

    def test_action_requires_post(self):
        self.client.force_login(self.super)
        resp = self.client.get(reverse("cabinet:review_approve", args=[self.review.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_list_filter_pending(self):
        self.client.force_login(self.super)
        Review.objects.create(name="Одобренный", rating=5, text="t",
                              status=Review.Status.APPROVED)
        resp = self.client.get(reverse("cabinet:review_list") + "?status=approved")
        self.assertContains(resp, "Одобренный")
        self.assertNotContains(resp, "Клиент")
