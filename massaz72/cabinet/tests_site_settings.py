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


class CabinetSpecialistRolesTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("role-admin")
        self.editor = user_model.objects.create_user("role-editor", is_staff=True)
        self.specialist = Specialist.objects.create(
            user=self.editor, name="Редактор", is_active=False,
        )
        self.unlinked = Specialist.objects.create(name="Без аккаунта")
        self.permission = Permission.objects.get(
            content_type__app_label="main", codename="manage_site_in_cabinet",
        )
        self.list_url = reverse("cabinet:specialists")
        self.roles_url = reverse("cabinet:specialist_roles", args=[self.specialist.pk])

    def test_superuser_lists_active_inactive_and_unlinked_specialists(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.list_url)
        self.assertContains(response, "Редактор")
        self.assertContains(response, "Без аккаунта")
        self.assertContains(response, "Неактивный специалист")
        self.assertContains(response, reverse("cabinet:site_settings"))
        self.assertEqual(self.client.get(reverse("cabinet:site_settings")).status_code, 200)

    def test_non_superuser_cannot_open_or_submit_roles_even_with_site_permission(self):
        self.editor.user_permissions.add(self.permission)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.get(self.roles_url).status_code, 403)
        self.assertEqual(self.client.post(self.roles_url, {"can_manage_reviews": "on"}).status_code, 403)
        self.specialist.refresh_from_db()
        self.assertFalse(self.specialist.can_manage_reviews)

    def test_superuser_can_grant_and_revoke_individual_roles(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.roles_url), "Управление настройками сайта")
        response = self.client.post(self.roles_url, {
            "can_manage_reviews": "on", "can_manage_site": "on",
        })
        self.assertRedirects(response, self.list_url)
        self.specialist.refresh_from_db()
        self.assertFalse(self.specialist.can_manage_prices)
        self.assertTrue(self.specialist.can_manage_reviews)
        self.assertTrue(self.editor.user_permissions.filter(pk=self.permission.pk).exists())

        self.client.force_login(self.editor)
        self.assertContains(self.client.get(reverse("cabinet:index")), reverse("cabinet:site_settings"))
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(self.roles_url, {}), self.list_url)
        self.specialist.refresh_from_db()
        self.assertFalse(self.specialist.can_manage_reviews)
        self.assertFalse(self.editor.user_permissions.filter(pk=self.permission.pk).exists())

    def test_group_permission_is_preserved_and_disclosed(self):
        group = Group.objects.create(name="Редакторы")
        group.permissions.add(self.permission)
        self.editor.groups.add(group)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.roles_url), "также выдан через группу")
        self.assertRedirects(self.client.post(self.roles_url, {}), self.list_url)
        self.assertTrue(self.editor.has_perm("main.manage_site_in_cabinet"))

    def test_cannot_edit_unlinked_or_superuser_accounts(self):
        admin_profile = Specialist.objects.create(user=self.admin, name="Администратор")
        self.client.force_login(self.admin)
        for profile in (self.unlinked, admin_profile):
            url = reverse("cabinet:specialist_roles", args=[profile.pk])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_roles_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.roles_url, {}).status_code, 403)
