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

    def test_editor_can_copy_default_and_existing_text_without_publishing(self):
        self.grant_access()
        response = self.client.get(self.url, {"edit_privacy": "1"})
        text = response.context["form"]["privacy_body"].value()
        self.assertIn("1. Общие положения", text)
        self.assertIn("IP-адрес", text)
        self.assertNotIn("<table>", text)
        self.site.refresh_from_db()
        self.assertEqual(self.site.privacy_body, "")

        self.site.privacy_body = "Действующая редакция"
        self.site.save(update_fields=["privacy_body"])
        response = self.client.get(self.url, {"edit_privacy": "1"})
        self.assertEqual(response.context["form"]["privacy_body"].value(), self.site.privacy_body)

    def test_editor_can_publish_policy_text(self):
        self.grant_access()
        self.assertContains(self.client.get(self.url), 'name="privacy_body"')
        response = self.client.post(self.url, self.form_data(
            privacy_body="Текст редакции", privacy_updated_at="2026-11-19",
        ))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        published = self.client.get(reverse("main:privacy"))
        self.assertContains(published, "Текст редакции")
        self.assertContains(published, "19.11.2026")

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
        self.assertContains(self.client.get(self.roles_url), "также выдано через группу")
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


class CabinetSpecialistLifecycleTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("lifecycle-admin")
        self.user = user_model.objects.create_user("lifecycle-specialist", is_staff=True)
        self.existing = Specialist.objects.create(user=self.user, name="Текущий профиль")
        self.add_url = reverse("cabinet:specialist_add")
        self.status_url = reverse("cabinet:specialist_status", args=[self.existing.pk])
        self.list_url = reverse("cabinet:specialists")
        self.client.force_login(self.admin)

    def test_superuser_adds_inactive_profile_without_account(self):
        self.assertContains(self.client.get(self.list_url), self.add_url)
        self.assertContains(self.client.get(self.add_url), "Добавить специалиста")
        response = self.client.post(self.add_url, {"name": "Новый профиль", "is_active": "on"})
        self.assertRedirects(response, self.list_url)
        specialist = Specialist.objects.get(name="Новый профиль")
        self.assertFalse(specialist.is_active)
        self.assertIsNone(specialist.user_id)

    def test_invalid_creation_does_not_add_profile(self):
        self.assertEqual(self.client.post(self.add_url, {"name": ""}).status_code, 200)
        self.assertEqual(Specialist.objects.count(), 1)

    def test_status_changes_are_idempotent_and_keep_account(self):
        for status, expected in (("inactive", False), ("inactive", False), ("active", True)):
            self.assertRedirects(self.client.post(self.status_url, {"status": status}), self.list_url)
            self.existing.refresh_from_db()
            self.assertEqual(self.existing.is_active, expected)
            self.assertEqual(self.existing.user_id, self.user.pk)

    def test_invalid_status_and_get_cannot_change_profile(self):
        self.assertEqual(self.client.post(self.status_url, {"status": "invalid"}).status_code, 400)
        self.assertEqual(self.client.get(self.status_url).status_code, 405)
        self.existing.refresh_from_db()
        self.assertTrue(self.existing.is_active)

    def test_staff_cannot_create_or_change_status(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.add_url).status_code, 403)
        self.assertEqual(self.client.post(self.add_url, {"name": "Новый профиль"}).status_code, 403)
        self.assertEqual(self.client.post(self.status_url, {"status": "inactive"}).status_code, 403)
        self.assertEqual(Specialist.objects.count(), 1)
        self.existing.refresh_from_db()
        self.assertTrue(self.existing.is_active)

    def test_changes_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.add_url, {"name": "Новый профиль"}).status_code, 403)
        self.assertEqual(client.post(self.status_url, {"status": "inactive"}).status_code, 403)

    def test_superuser_can_delegate_profile_management_without_role_management(self):
        permission = Permission.objects.get(
            content_type__app_label="cabinet", codename="manage_specialist_profiles",
        )
        roles_url = reverse("cabinet:specialist_roles", args=[self.existing.pk])
        admin_profile = Specialist.objects.create(user=self.admin, name="Администратор")
        admin_status_url = reverse("cabinet:specialist_status", args=[admin_profile.pk])
        self.assertRedirects(
            self.client.post(roles_url, {"can_manage_specialists": "on"}), self.list_url,
        )
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.list_url), self.add_url)
        self.assertRedirects(self.client.post(self.add_url, {"name": "Новый профиль"}), self.list_url)
        self.assertRedirects(self.client.post(self.status_url, {"status": "inactive"}), self.list_url)
        self.assertEqual(self.client.post(admin_status_url, {"status": "inactive"}).status_code, 403)
        self.assertEqual(self.client.post(roles_url, {"can_manage_site": "on"}).status_code, 403)

        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(roles_url, {}), self.list_url)
        self.assertFalse(self.user.user_permissions.filter(pk=permission.pk).exists())
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
