from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from cabinet.models import Specialist
from main.context_processors import _account_identity


class AccountIdentityTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _identity(self, user):
        req = self.rf.get("/")
        req.user = user
        return _account_identity(req)

    def test_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(self._identity(AnonymousUser()), ("", ""))

    def test_specialist_name_initials(self):
        u = User.objects.create_user("igor", password="pw")
        Specialist.objects.create(user=u, name="Пономарёв Игорь")
        name, initials = self._identity(u)
        self.assertEqual(name, "Пономарёв Игорь")
        self.assertEqual(initials, "ПИ")  # фамилия + имя

    def test_full_name_initials(self):
        u = User.objects.create_user("c", password="pw", first_name="Иван", last_name="Петров")
        name, initials = self._identity(u)
        self.assertEqual(name, "Иван Петров")
        self.assertEqual(initials, "ИП")

    def test_single_word_name(self):
        u = User.objects.create_user("m", password="pw")
        Specialist.objects.create(user=u, name="Марина")
        _, initials = self._identity(u)
        self.assertEqual(initials, "М")

    def test_username_fallback(self):
        u = User.objects.create_user("bob", password="pw")
        name, initials = self._identity(u)
        self.assertEqual(name, "bob")
        self.assertEqual(initials, "B")
