from django.test import TestCase
from django.urls import reverse

from cabinet.models import Specialist
from main.models import SiteSettings
from main.policy import build_policy_context
from tgbot.models import BotSettings


def _page(testcase):
    return testcase.client.get(reverse("main:privacy")).content.decode()


def _specialist(**kw):
    kw.setdefault("name", "Тест")
    return Specialist.objects.create(**kw)


class PolicyContextTest(TestCase):
    def test_defaults_without_site_settings(self):
        p = build_policy_context()
        self.assertEqual(p.operator_name, "Пономарев Игорь Валерьевич")
        self.assertEqual(p.operator_email, "info@massaz72.ru")
        self.assertFalse(p.booking_enabled)
        self.assertFalse(p.cabinet_enabled)
        self.assertFalse(p.reviews_enabled)
        self.assertEqual(p.messengers, "")
        self.assertFalse(p.foreign_transfer)

    def test_flags_follow_site_settings(self):
        SiteSettings.objects.create(
            online_booking_enabled=True, client_cabinet_enabled=True, reviews_enabled=True
        )
        p = build_policy_context()
        self.assertTrue(p.booking_enabled)
        self.assertTrue(p.cabinet_enabled)
        self.assertTrue(p.reviews_enabled)

    def test_max_only_is_not_foreign(self):
        _specialist(max_messanger="abc", max_messanger_active=True)
        p = build_policy_context()
        self.assertEqual(p.messengers, "MAX")
        self.assertFalse(p.foreign_transfer)

    def test_telegram_and_whatsapp_are_foreign(self):
        _specialist(
            telegram_username="tg", telegram_active=True,
            whatsapp_number="79000000000", whatsapp_active=True,
            max_messanger="abc", max_messanger_active=True,
        )
        p = build_policy_context()
        self.assertEqual(p.messengers, "Telegram, WhatsApp, MAX")
        self.assertTrue(p.foreign_transfer)
        self.assertEqual(p.foreign_services, "Telegram, WhatsApp")

    def test_inactive_messenger_or_specialist_ignored(self):
        _specialist(telegram_username="tg", telegram_active=False)
        _specialist(name="Б", whatsapp_number="79", whatsapp_active=True, is_active=False)
        p = build_policy_context()
        self.assertEqual(p.messengers, "")
        self.assertFalse(p.foreign_transfer)

    def test_enabled_bot_counts_as_telegram(self):
        BotSettings.objects.create(is_enabled=True, bot_username="massaz_bot")
        p = build_policy_context()
        self.assertEqual(p.messengers, "Telegram")
        self.assertTrue(p.foreign_transfer)

    def test_disabled_bot_ignored(self):
        BotSettings.objects.create(is_enabled=False, bot_username="massaz_bot")
        self.assertEqual(build_policy_context().messengers, "")


class PrivacyPageTest(TestCase):
    def test_operator_details_from_settings(self):
        SiteSettings.objects.create(
            operator_name="ИП Иванов И.И.", operator_inn="720000000000",
            operator_address="г. Тюмень, ул. Тестовая, 1",
            operator_email="mail@example.ru",
            retention_text="3 года после последнего обращения",
        )
        html = _page(self)
        for text in (
            "ИП Иванов И.И.", "ИНН 720000000000", "г. Тюмень, ул. Тестовая, 1",
            "mail@example.ru", "3 года после последнего обращения",
        ):
            self.assertIn(text, html)
        self.assertNotIn("info@massaz72.ru", html)

    def test_empty_optional_fields_not_rendered(self):
        html = _page(self)
        self.assertNotIn("ИНН", html)
        self.assertNotIn("адрес:", html)
        self.assertNotIn("по телефону", html)
        self.assertNotIn("Дата последней редакции", html)
        self.assertNotIn("{{", html)
        self.assertNotIn("{%", html)

    def test_updated_date_shown(self):
        import datetime
        SiteSettings.objects.create(privacy_updated_at=datetime.date(2026, 10, 13))
        self.assertIn("Дата последней редакции: 13.10.2026", _page(self))

    def test_sections_hidden_when_features_off(self):
        SiteSettings.objects.create()
        html = _page(self)
        self.assertNotIn("Приём и обработка заявок на запись", html)
        self.assertNotIn("личного кабинета клиента", html)
        self.assertNotIn("Приём, проверка и публикация отзывов", html)
        self.assertNotIn("Связь с клиентом и ответы на обращения", html)
        self.assertNotIn("сведения о состоянии здоровья", html)
        self.assertIn("Оператор не осуществляет трансграничную передачу", html)

    def test_sections_shown_when_features_on(self):
        SiteSettings.objects.create(
            online_booking_enabled=True, client_cabinet_enabled=True, reviews_enabled=True
        )
        html = _page(self)
        self.assertIn("Приём и обработка заявок на запись", html)
        self.assertIn("личного кабинета клиента", html)
        self.assertIn("Приём, проверка и публикация отзывов", html)
        self.assertNotIn("сведения о состоянии здоровья", html)

    def test_max_only_no_cross_border(self):
        _specialist(max_messanger="abc")
        html = _page(self)
        self.assertIn("Связь с клиентом и ответы на обращения через мессенджеры (MAX)", html)
        self.assertIn("Оператор не осуществляет трансграничную передачу", html)

    def test_telegram_adds_cross_border_section(self):
        _specialist(telegram_username="tg")
        html = _page(self)
        self.assertIn("через Telegram данные могут передаваться на серверы", html)
        self.assertNotIn("Оператор не осуществляет трансграничную передачу", html)

    def test_always_has_core_section(self):
        html = _page(self)
        self.assertIn("IP-адрес", html)
        self.assertIn("Срок обработки и хранения:", html)


def _consent(testcase):
    return testcase.client.get(reverse("main:consent")).content.decode()


class ConsentPageTest(TestCase):
    def test_operator_details_same_as_policy(self):
        SiteSettings.objects.create(
            operator_name="ИП Иванов И.И.", operator_inn="720000000000",
            operator_address="г. Тюмень, ул. Тестовая, 1",
            operator_email="mail@example.ru",
            retention_text="3 года после последнего обращения",
        )
        consent, policy = _consent(self), _page(self)
        for text in (
            "ИП Иванов И.И.", "ИНН 720000000000", "г. Тюмень, ул. Тестовая, 1",
            "mail@example.ru", "3 года после последнего обращения",
        ):
            self.assertIn(text, consent)
            self.assertIn(text, policy)
        self.assertNotIn("info@massaz72.ru", consent)

    def test_empty_optional_fields_not_rendered(self):
        html = _consent(self)
        self.assertNotIn("ИНН", html)
        self.assertNotIn("адрес:", html)
        self.assertNotIn("Дата последней редакции", html)
        self.assertNotIn("{{", html)
        self.assertNotIn("{%", html)

    def test_updated_date_shown(self):
        import datetime
        SiteSettings.objects.create(privacy_updated_at=datetime.date(2026, 10, 13))
        self.assertIn("Дата последней редакции: 13.10.2026", _consent(self))

    def test_purposes_follow_enabled_features(self):
        SiteSettings.objects.create()
        html = _consent(self)
        self.assertNotIn("приём и обработка заявки на запись", html)
        self.assertNotIn("личного кабинета", html)
        self.assertNotIn("публикация моего отзыва", html)
        self.assertNotIn("Отдельное согласие на сведения о состоянии здоровья", html)
        self.assertIn("обеспечение работы и безопасности сайта", html)

        SiteSettings.objects.update(
            online_booking_enabled=True, client_cabinet_enabled=True, reviews_enabled=True
        )
        html = _consent(self)
        self.assertIn("приём и обработка заявки на запись", html)
        self.assertIn("личного кабинета", html)
        self.assertIn("публикация моего отзыва", html)
        self.assertNotIn('id="health"', html)
        self.assertNotIn("комментарий к заявке", html)

    def test_messengers_and_cross_border(self):
        _specialist(max_messanger="abc")
        html = _consent(self)
        self.assertIn("мессенджеры (MAX)", html)
        self.assertNotIn("за пределами Российской Федерации", html)
        _specialist(name="Б", telegram_username="tg")
        html = _consent(self)
        self.assertIn("при обращении через Telegram данные могут передаваться", html)

    def test_links_to_policy(self):
        self.assertIn(reverse("main:privacy"), _consent(self))


class EditablePrivacyPageTest(TestCase):
    def test_custom_text_is_escaped_and_does_not_replace_consent(self):
        site = SiteSettings.objects.create(privacy_body="Новая редакция\n\n<script>test</script>")
        response = self.client.get(reverse("main:privacy"))
        self.assertContains(response, "<p>Новая редакция</p>", html=True)
        self.assertContains(response, "&lt;script&gt;test&lt;/script&gt;")
        self.assertNotContains(response, "<script>test</script>")
        self.assertContains(response, site.operator_email)
        self.assertNotContains(response, "Основные понятия")
        self.assertNotContains(self.client.get(reverse("main:consent")), "Новая редакция")

        site.privacy_body = ""
        site.save(update_fields=["privacy_body"])
        self.assertContains(self.client.get(reverse("main:privacy")), "Основные понятия")
