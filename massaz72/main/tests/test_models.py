import os
import shutil
import tempfile
from datetime import date, datetime
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from main.models import About, Certificate, SiteSettings


class TempMediaRootMixin:
    """Подменяет MEDIA_ROOT на временную папку только для своего класса
    и удаляет её после тестов: файлы не попадают в media/ и в репозиторий,
    а подмена не «протекает» в другие тесты."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()


class AboutModelTest(TestCase):
    def setUp(self):
        """Создаем тестовые данные"""
        self.about = About.objects.create(
            name="Тест Тестович",
            description="Тестовое описание",
            start_date=date(2020, 1, 1),
            is_active=True,
            order=1,
        )

    def test_str_representation(self):
        """Тест строкового представления модели"""
        self.assertEqual(str(self.about), "Тест Тестович")

    def test_experience_calculation(self):
        """Тест расчета опыта работы"""
        with patch("datetime.date") as mock_date:
            mock_date.today.return_value = date(2024, 3, 23)
            self.assertEqual(self.about.experience, 4)

    def test_experience_without_start_date(self):
        """Тест опыта работы без даты начала"""
        about = About.objects.create(name="Без опыта", description="Тестовое описание")
        self.assertEqual(about.experience, 0)

    def test_experience_text_formatting(self):
        """Тест форматирования текста опыта работы"""
        # Фиксируем текущую дату для теста
        fixed_date = date(2024, 3, 23)  # используем фиксированную дату

        test_cases = [
            (date(2023, 3, 23), "1 год"),
            (date(2022, 3, 23), "2 года"),
            (date(2019, 3, 23), "5 лет"),
            (date(2013, 3, 23), "11 лет"),
            (date(2003, 3, 23), "21 год"),
            (date(2002, 3, 23), "22 года"),
            (date(1999, 3, 23), "25 лет"),
        ]

        for test_date, expected in test_cases:
            with self.subTest(test_date=test_date):
                self.about.start_date = test_date
                self.about.save()
                # Подменяем date.today() на нашу фиксированную дату
                with patch("datetime.date") as mock_date:
                    mock_date.today.return_value = fixed_date
                    self.assertEqual(self.about.experience_text, expected)

    def test_default_values(self):
        """Тест значений по умолчанию"""
        about = About.objects.create(name="Тест")
        self.assertTrue(about.is_active)
        self.assertEqual(about.order, 0)
        self.assertIsInstance(about.created_at, datetime)
        self.assertIsInstance(about.updated_at, datetime)


class CertificateModelTest(TempMediaRootMixin, TestCase):
    def setUp(self):
        """Создаем тестовые данные"""
        self.about = About.objects.create(
            name="Тест Тестович", description="Тестовое описание"
        )

        # Создаем тестовый файл
        self.test_image = SimpleUploadedFile(
            name="test_image.jpg",
            content=b"x" * 10,  # маленький тестовый файл
            content_type="image/jpeg",
        )

        self.certificate = Certificate.objects.create(
            about=self.about,
            title="Тестовый сертификат",
            image=self.test_image,
            date_received=date(2022, 1, 1),
            order=1,
        )

    def test_str_representation(self):
        """Тест строкового представления модели"""
        self.assertEqual(str(self.certificate), "Тестовый сертификат")

    def test_default_values(self):
        """Тест значений по умолчанию"""
        certificate = Certificate.objects.create(
            about=self.about, title="Тест", image=self.test_image
        )
        self.assertEqual(certificate.order, 0)
        self.assertFalse(certificate.is_archived)
        self.assertIsInstance(certificate.created_at, datetime)

    def test_file_size_validation(self):
        """Тест валидации размера файла"""
        # Создаем файл большего размера, чем разрешено
        large_file = SimpleUploadedFile(
            name="large_file.jpg",
            content=b"x" * (6 * 1024 * 1024),  # 6MB
            content_type="image/jpeg",
        )

        with self.assertRaises(ValidationError):
            certificate = Certificate(
                about=self.about, title="Большой файл", image=large_file
            )
            certificate.full_clean()

    def test_related_name(self):
        """Тест related_name для связи с About"""
        certificate = self.about.certificates.first()
        self.assertEqual(certificate, self.certificate)

    def test_ordering(self):
        """Тест сортировки сертификатов"""
        Certificate.objects.create(
            about=self.about, title="Второй сертификат", image=self.test_image, order=0
        )
        certificates = Certificate.objects.all()
        self.assertEqual(certificates[0].title, "Второй сертификат")
        self.assertEqual(certificates[1].title, "Тестовый сертификат")


class SiteSettingsTest(TempMediaRootMixin, TestCase):
    def setUp(self):
        """Создаем тестовые данные"""
        self.settings = SiteSettings.objects.create(
            head_title="Тестовый заголовок",
            main_title="Главный заголовок",
            main_subtitle="Подзаголовок",
            child_massage_title="Детский массаж",
            massage_title="Массаж",
            about_title="Обо мне",
            contact_title="Контакты",
        )

    def test_str_representation(self):
        """Тест строкового представления модели"""
        self.assertEqual(str(self.settings), "Настройки")

    def test_default_values(self):
        """Тест значений по умолчанию"""
        settings = SiteSettings.objects.create()
        self.assertEqual(settings.head_title, "Детский массаж в Тюмени | Женский массаж")
        self.assertEqual(settings.main_title, "Детский и женский массаж в Тюмени")
        self.assertEqual(settings.main_subtitle, "Твой массажист - забота о Вашем здоровье")
        self.assertEqual(settings.child_massage_title, "Детский массаж")
        self.assertEqual(settings.massage_title, "Массаж")
        self.assertEqual(settings.about_title, "Обо мне")
        self.assertEqual(settings.contact_title, "Контакты")
        self.assertIsNone(settings.price_change_date)

    def test_background_upload(self):
        """Тест загрузки фонового изображения"""
        test_image = SimpleUploadedFile(
            name="test_background.jpg", content=b"x" * 10, content_type="image/jpeg"
        )
        self.settings.background = test_image
        self.settings.save()
        self.assertTrue(self.settings.background)
        self.assertTrue(os.path.exists(self.settings.background.path))

    def test_verbose_names(self):
        """Тест verbose_names"""
        self.assertEqual(SiteSettings._meta.verbose_name, "Настройки сайта")
        self.assertEqual(SiteSettings._meta.verbose_name_plural, "Настройки сайта")
