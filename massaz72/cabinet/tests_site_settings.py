from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from main.forms import CabinetSiteSettingsForm
from main.models import SiteSettings

from .models import Specialist


class CabinetSiteSettingsTest(TestCase):
    def setUp(self):
        self.site = SiteSettings.objects.create()
        self.user = get_user_model().objects.create_user("site-editor")
        Specialist.objects.create(user=self.user, name="Специалист")
        self.url = reverse("cabinet:site_settings")

    def grant_access(self):
        group = Group.objects.create(name="Редакторы сайта")
        group.permissions.add(Permission.objects.get(
            content_type__app_label="main", codename="manage_site_in_cabinet",
        ))
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def form_data(self, **changes):
        data = {
            name: value for name, value in CabinetSiteSettingsForm(instance=self.site).initial.items()
            if value is not None and name not in {"background", "social_cover"}
        }
        data.update(changes)
        return data

    def test_anonymous_is_redirected(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url).status_code, 302)

    def test_specialist_without_permission_cannot_view_or_change_settings(self):
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("cabinet:settings")), self.url)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.form_data(main_title="Подмена")).status_code, 403)
        for endpoint in ("booking_toggle", "client_cabinet_toggle"):
            self.assertEqual(self.client.post(reverse(f"cabinet:{endpoint}")).status_code, 403)
        self.site.refresh_from_db()
        self.assertNotEqual(self.site.main_title, "Подмена")
        self.assertFalse(self.site.online_booking_enabled)
        self.assertFalse(self.site.client_cabinet_enabled)

    def test_group_editor_can_update_and_clear_cover(self):
        self.grant_access()
        self.assertFalse(self.user.is_staff)
        self.assertContains(self.client.get(reverse("cabinet:settings")), self.url)
        self.assertContains(self.client.get(self.url), 'enctype="multipart/form-data"')

        image = BytesIO()
        Image.new("RGB", (120, 63)).save(image, "JPEG")
        cover = SimpleUploadedFile("cover.jpg", image.getvalue())
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            response = self.client.post(self.url, self.form_data(main_title="Новый заголовок", social_cover=cover))
            self.assertRedirects(response, self.url, fetch_redirect_response=False)
            self.site.refresh_from_db()
            self.assertEqual(self.site.main_title, "Новый заголовок")
            self.assertTrue(self.site.social_cover.storage.exists(self.site.social_cover.name))
            homepage = self.client.get(reverse("main:index"), secure=True)
            self.assertContains(homepage, f'content="https://testserver{self.site.social_cover.url}"')

            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, self.form_data(**{"social_cover-clear": "on"}))
            self.assertRedirects(response, self.url, fetch_redirect_response=False)
            self.assertFalse(self.site.social_cover.storage.exists(self.site.social_cover.name))
            self.site.refresh_from_db()
            self.assertFalse(self.site.social_cover)

    def test_invalid_upload_does_not_save_other_fields(self):
        self.grant_access()
        image = BytesIO()
        Image.new("RGB", (120, 63)).save(image, "GIF")
        response = self.client.post(self.url, self.form_data(
            main_title="Новый заголовок",
            social_cover=SimpleUploadedFile("cover.jpg", image.getvalue()),
        ))
        self.assertContains(response, "Загрузите файл JPEG или PNG")
        self.site.refresh_from_db()
        self.assertNotEqual(self.site.main_title, "Новый заголовок")

    def test_post_requires_csrf(self):
        self.grant_access()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.form_data()).status_code, 403)
