from django.test import TestCase
from services.models import Massage, Category
from django.core.exceptions import ValidationError

class MassageModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Тестовая категория",
            description="Описание тестовой категории"
        )
        self.massage = Massage.objects.create(
            name="Тестовый массаж",
            price=1000.00,
            description="Описание тестового массажа",
            duration_min=30,
            duration_max=60,
            massage_type='adult',
            order=1,
            category=self.category
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
                massage_type='adult',
                order=2,
                category=self.category
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
                massage_type='adult',
                order=2,
                category=self.category
            )
            massage.full_clean()

class CategoryModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Тестовая категория",
            description="Описание тестовой категории"
        )

    def test_category_creation(self):
        """Тест создания категории"""
        self.assertTrue(isinstance(self.category, Category))
        self.assertEqual(str(self.category), "Тестовая категория")

    def test_category_massages(self):
        """Тест связи категории с массажами"""
        Massage.objects.create(
            name="Массаж 1",
            price=1000.00,
            description="Описание",
            duration_min=30,
            duration_max=60,
            massage_type='adult',
            order=1,
            category=self.category
        )
        Massage.objects.create(
            name="Массаж 2",
            price=1500.00,
            description="Описание",
            duration_min=45,
            duration_max=90,
            massage_type='adult',
            order=2,
            category=self.category
        )
        self.assertEqual(self.category.massage_set.count(), 2) 