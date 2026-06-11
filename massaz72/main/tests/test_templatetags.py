from django.test import SimpleTestCase

from main.templatetags.main_tags import russian_plural

MASSAGE = "массаж,массажа,массажей"


class RussianPluralTest(SimpleTestCase):
    def test_one(self):
        self.assertEqual(russian_plural(1, MASSAGE), "массаж")
        self.assertEqual(russian_plural(21, MASSAGE), "массаж")
        self.assertEqual(russian_plural(101, MASSAGE), "массаж")

    def test_few(self):
        for n in (2, 3, 4, 22, 33, 104):
            self.assertEqual(russian_plural(n, MASSAGE), "массажа", n)

    def test_many(self):
        for n in (0, 5, 6, 10, 25, 100):
            self.assertEqual(russian_plural(n, MASSAGE), "массажей", n)

    def test_teens_are_many(self):
        # 11–14 — исключение: всегда форма "много", несмотря на последнюю цифру
        for n in (11, 12, 13, 14, 111, 112):
            self.assertEqual(russian_plural(n, MASSAGE), "массажей", n)

    def test_string_number(self):
        self.assertEqual(russian_plural("2", MASSAGE), "массажа")

    def test_invalid_falls_back_to_many(self):
        self.assertEqual(russian_plural(None, MASSAGE), "массажей")
        self.assertEqual(russian_plural("x", MASSAGE), "массажей")
