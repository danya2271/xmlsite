from datetime import date, timedelta

from django.test import SimpleTestCase

from contacts.forms import ContactForm

from .helpers import CONTACT


class ContactFormTests(SimpleTestCase):
    def form(self, **changes):
        return ContactForm({**CONTACT.as_dict(), "file_format": "xml", **changes})

    def test_valid_contact(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.to_contact(), CONTACT)

    def test_phone_or_email_is_required(self):
        self.assertFalse(self.form(phone="", email="").is_valid())
        self.assertTrue(self.form(phone="").is_valid())
        self.assertTrue(self.form(email="").is_valid())

    def test_names_are_validated(self):
        for name in ["", "123", "<script>", "Анна_тест"]:
            with self.subTest(name=name):
                self.assertFalse(self.form(first_name=name).is_valid())
        self.assertTrue(self.form(first_name="Анна-Мария", last_name="О’Коннор").is_valid())

    def test_invalid_emails(self):
        for email in ["not-an-email", "test@", "a b@example.com"]:
            with self.subTest(email=email):
                self.assertFalse(self.form(email=email).is_valid())

    def test_invalid_phones(self):
        for phone in ["123", "+7 abc 1234567", "1234567890123456", "++79991234567"]:
            with self.subTest(phone=phone):
                self.assertFalse(self.form(phone=phone).is_valid())

    def test_invalid_birthday(self):
        for birthday in ["1899-12-31", "2000-02-30", "31.12.2000", str(date.today() + timedelta(days=1))]:
            with self.subTest(birthday=birthday):
                self.assertFalse(self.form(birthday=birthday).is_valid())

    def test_database_target_does_not_require_file_format(self):
        form = ContactForm({**CONTACT.as_dict(), "storage_target": "database", "file_format": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["storage_target"], "database")

    def test_invalid_category_and_format(self):
        self.assertFalse(self.form(category="unknown").is_valid())
        self.assertFalse(self.form(file_format="html").is_valid())

    def test_field_limits(self):
        self.assertFalse(self.form(notes="text" * 251).is_valid())
        self.assertFalse(self.form(first_name="А" * 81).is_valid())

    def test_control_characters_are_rejected(self):
        self.assertFalse(self.form(notes="hello\x01world").is_valid())

    def test_invalid_form_cannot_create_contact(self):
        with self.assertRaises(ValueError):
            self.form(first_name="").to_contact()
