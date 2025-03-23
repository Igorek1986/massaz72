from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import date, timedelta, datetime
from main.models import About, Certificate
import os
from django.conf import settings
import shutil
from unittest.mock import patch

class AboutModelTest(TestCase):
    def setUp(self):
        """Создаем тестовые данные"""
        self.about = About.objects.create(
            name="Тест Тестович",
            description="Тестовое описание",
            start_date=date(2020, 1, 1),
            is_active=True,
            order=1
        )

    def test_str_representation(self):
        """Тест строкового представления модели"""
        self.assertEqual(str(self.about), "Тест Тестович")

    def test_experience_calculation(self):
        """Тест расчета опыта работы"""
        with patch('datetime.date') as mock_date:
            mock_date.today.return_value = date(2024, 3, 23)
            self.assertEqual(self.about.experience, 4)

    def test_experience_without_start_date(self):
        """Тест опыта работы без даты начала"""
        about = About.objects.create(
            name="Без опыта",
            description="Тестовое описание"
        )
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
            (date(1999, 3, 23), "25 лет")
        ]
        
        for test_date, expected in test_cases:
            with self.subTest(test_date=test_date):
                self.about.start_date = test_date
                self.about.save()
                # Подменяем date.today() на нашу фиксированную дату
                with patch('datetime.date') as mock_date:
                    mock_date.today.return_value = fixed_date
                    self.assertEqual(self.about.experience_text, expected)

    def test_default_values(self):
        """Тест значений по умолчанию"""
        about = About.objects.create(name="Тест")
        self.assertTrue(about.is_active)
        self.assertEqual(about.order, 0)
        self.assertIsInstance(about.created_at, datetime)
        self.assertIsInstance(about.updated_at, datetime)

class CertificateModelTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Создаем временную директорию для медиафайлов
        settings.MEDIA_ROOT = os.path.join(settings.BASE_DIR, 'test_media')
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        # Удаляем временную директорию
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        """Создаем тестовые данные"""
        self.about = About.objects.create(
            name="Тест Тестович",
            description="Тестовое описание"
        )
        
        # Создаем тестовый файл
        self.test_image = SimpleUploadedFile(
            name='test_image.jpg',
            content=b'x' * 10,  # маленький тестовый файл
            content_type='image/jpeg'
        )
        
        self.certificate = Certificate.objects.create(
            about=self.about,
            title="Тестовый сертификат",
            image=self.test_image,
            date_received=date(2022, 1, 1),
            order=1
        )

    def test_str_representation(self):
        """Тест строкового представления модели"""
        self.assertEqual(str(self.certificate), "Тестовый сертификат")

    def test_default_values(self):
        """Тест значений по умолчанию"""
        certificate = Certificate.objects.create(
            about=self.about,
            title="Тест",
            image=self.test_image
        )
        self.assertEqual(certificate.order, 0)
        self.assertFalse(certificate.is_archived)
        self.assertIsInstance(certificate.created_at, datetime)

    def test_file_size_validation(self):
        """Тест валидации размера файла"""
        # Создаем файл большего размера, чем разрешено
        large_file = SimpleUploadedFile(
            name='large_file.jpg',
            content=b'x' * (6 * 1024 * 1024),  # 6MB
            content_type='image/jpeg'
        )
        
        with self.assertRaises(ValidationError):
            certificate = Certificate(
                about=self.about,
                title="Большой файл",
                image=large_file
            )
            certificate.full_clean()

    def test_related_name(self):
        """Тест related_name для связи с About"""
        certificate = self.about.certificates.first()
        self.assertEqual(certificate, self.certificate)

    def test_ordering(self):
        """Тест сортировки сертификатов"""
        Certificate.objects.create(
            about=self.about,
            title="Второй сертификат",
            image=self.test_image,
            order=0
        )
        certificates = Certificate.objects.all()
        self.assertEqual(certificates[0].title, "Второй сертификат")
        self.assertEqual(certificates[1].title, "Тестовый сертификат") 