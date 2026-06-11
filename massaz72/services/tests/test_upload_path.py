"""Безопасность путей загрузки: get_file_path не должен сохранять файлы
с активными расширениями (.html, .svg и т.п.), иначе файл из /media/
может быть отдан браузеру как HTML → stored XSS."""

from django.test import SimpleTestCase

from massaz72.utils import get_file_path
from services.models import Massage


def _massage(massage_type="adult"):
    return Massage(name="Спина", massage_type=massage_type)


class UploadPathExtensionTest(SimpleTestCase):
    def test_allowed_extension_kept_and_lowercased(self):
        path = get_file_path(_massage(), "фото.PNG")
        self.assertTrue(path.endswith(".png"), path)

    def test_html_extension_replaced(self):
        path = get_file_path(_massage(), "evil.html")
        self.assertTrue(path.endswith(".jpg"), path)

    def test_svg_extension_replaced(self):
        path = get_file_path(_massage(), "image.svg")
        self.assertTrue(path.endswith(".jpg"), path)

    def test_double_extension_uses_last_part(self):
        path = get_file_path(_massage(), "photo.jpg.html")
        self.assertTrue(path.endswith(".jpg"), path)

    def test_no_extension_falls_back(self):
        path = get_file_path(_massage(), "noext")
        self.assertTrue(path.endswith(".jpg"), path)

    def test_folder_by_massage_type(self):
        self.assertTrue(get_file_path(_massage("adult"), "a.jpg").startswith("massages/adults/"))
        self.assertTrue(get_file_path(_massage("child"), "a.jpg").startswith("massages/children/"))
