from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from contacts.domain import Contact


CONTACT = Contact(
    first_name="Анна",
    last_name="Соколова",
    phone="+7 (900) 123-45-67",
    email="anna@example.com",
    company="Студия Форма",
    city="Екатеринбург",
    category="work",
    birthday="1998-04-12",
    notes="Обсудить проект & детали <встречи>.",
)


class StorageTestCase(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.storage = Path(self.temporary_directory.name) / "contacts"
        self.settings_override = override_settings(CONTACTS_STORAGE_DIR=self.storage)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
