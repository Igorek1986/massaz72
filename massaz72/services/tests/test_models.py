from django.test import TestCase
from services.models import Massage
from django.core.exceptions import ValidationError


class MassageModelTest(TestCase):
    """
    Тесты для модели Massage
    """

    def setUp(self):
        self.massage = Massage.objects.create(
            name="Тестовый массаж",
            price=1000,
            description="Описание",
            duration_min=30,
            duration_max=60,
            massage_type="adult",
            order=2,
            slug="test-massage",
            image=None,
        )

    def test_massage_creation(self):
        """Тест создания объекта массажа"""
        self.assertTrue(isinstance(self.massage, Massage))
        self.assertEqual(str(self.massage), "Тестовый массаж")

    def test_massage_price_validation(self):
        """Тест валидации цены массажа"""
        with self.assertRaises(ValidationError):
            massage = Massage(
                name="Невалидный массаж",
                price=-100,  # Отрицательная цена
                description="Описание",
                duration_min=30,
                duration_max=60,
                massage_type="adult",
                order=2,
            )
            massage.full_clean()

    def test_massage_duration_validation(self):
        """Тест валидации длительности массажа"""
        with self.assertRaises(ValidationError):
            massage = Massage(
                name="Невалидный массаж",
                price=1000,
                description="Описание",
                duration_min=60,  # Минимальная длительность больше максимальной
                duration_max=30,
                massage_type="adult",
                order=2,
            )
            massage.full_clean()
