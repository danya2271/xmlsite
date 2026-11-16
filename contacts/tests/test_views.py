from dataclasses import replace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from contacts.codecs import parse_contacts, serialize_contacts
from contacts.storage import save_contact

from .helpers import CONTACT, StorageTestCase


class ViewTests(StorageTestCase):
    def test_empty_state(self):
        response = self.client.get(reverse("contacts:index"))
        self.assertContains(response, "На сервере пока нет файлов")
        self.assertEqual(response.context["total_contacts"], 0)

    def test_create_pages_are_available(self):
        for name in ["contacts:create", "contacts:import"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_create_in_both_formats(self):
        for file_format in ["xml", "json"]:
            with self.subTest(file_format=file_format):
                response = self.client.post(reverse("contacts:create"), {**CONTACT.as_dict(), "file_format": file_format})
                self.assertRedirects(response, reverse("contacts:index"))
        response = self.client.get(reverse("contacts:index"))
        self.assertEqual(response.context["total_contacts"], 2)

    def test_invalid_contact_displays_errors_without_saving(self):
        response = self.client.post(reverse("contacts:create"), {"first_name": "123"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(self.storage.exists())

    def test_upload_and_list_both_formats(self):
        for file_format in ["xml", "json"]:
            upload = SimpleUploadedFile(f"contact.{file_format}", serialize_contacts([CONTACT], file_format))
            response = self.client.post(reverse("contacts:import"), {"file": upload}, follow=True)
            self.assertContains(response, CONTACT.full_name)
        self.assertEqual(response.context["total_contacts"], 2)

    def test_invalid_upload_shows_error_and_is_removed(self):
        upload = SimpleUploadedFile("broken.xml", b"<broken>")
        response = self.client.post(reverse("contacts:import"), {"file": upload})
        self.assertContains(response, "Некорректный")
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_empty_upload_shows_error(self):
        response = self.client.post(reverse("contacts:import"), {})
        self.assertTrue(response.context["form"].errors)

    def test_search_filters_and_statistics(self):
        save_contact(CONTACT, "xml")
        save_contact(replace(CONTACT, first_name="Михаил", last_name="Волков", category="friends"), "json")
        response = self.client.get(reverse("contacts:index"), {"q": "сОкОлОвА", "category": "work", "format": "xml"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["total_contacts"], 2)
        self.assertContains(response, "Анна Соколова")
        self.assertNotContains(response, "Михаил Волков")

    def test_no_search_results(self):
        response = self.client.get(reverse("contacts:index"), {"q": "nobody"})
        self.assertContains(response, "Ничего не нашлось")

    def test_pagination_preserves_filters(self):
        for position in range(13):
            save_contact(CONTACT, "xml")
        response = self.client.get(reverse("contacts:index"), {"q": "Анна", "format": "xml"})
        self.assertEqual(len(response.context["page_obj"]), 12)
        self.assertContains(response, "page=2")
        self.assertNotContains(response, 'href="??')
        response = self.client.get(reverse("contacts:index"), {"q": "Анна", "format": "xml", "page": 2})
        self.assertEqual(len(response.context["page_obj"]), 1)

    def test_download_and_conversion(self):
        filename = save_contact(CONTACT, "xml")
        response = self.client.get(reverse("contacts:download", args=[filename]))
        self.assertEqual(parse_contacts(response.content, "xml"), [CONTACT])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        response = self.client.get(reverse("contacts:download", args=[filename]), {"format": "json"})
        self.assertEqual(parse_contacts(response.content, "json"), [CONTACT])

    def test_missing_or_invalid_download_is_404(self):
        response = self.client.get(reverse("contacts:download", args=["missing.xml"]))
        self.assertEqual(response.status_code, 404)

    def test_export_all_to_both_formats(self):
        save_contact(CONTACT, "xml")
        save_contact(CONTACT, "json")
        for file_format in ["xml", "json"]:
            response = self.client.get(reverse("contacts:export", args=[file_format]))
            self.assertEqual(len(parse_contacts(response.content, file_format)), 2)

    def test_empty_export_returns_message(self):
        response = self.client.get(reverse("contacts:export", args=["xml"]), follow=True)
        self.assertContains(response, "Пока нечего экспортировать")

    @override_settings(MAX_CONTACTS_PER_FILE=1)
    def test_oversized_export_is_not_silently_truncated(self):
        save_contact(CONTACT, "xml")
        save_contact(CONTACT, "json")
        response = self.client.get(reverse("contacts:export", args=["xml"]), follow=True)
        self.assertContains(response, "не помещаются в один файл")

    def test_export_does_not_silently_skip_broken_files(self):
        save_contact(CONTACT, "xml")
        (self.storage / "broken.xml").write_text("broken")
        response = self.client.get(reverse("contacts:export", args=["json"]), follow=True)
        self.assertContains(response, "Экспорт отменён")

    def test_sample_files_are_valid(self):
        for file_format in ["xml", "json"]:
            response = self.client.get(reverse("contacts:sample", args=[file_format]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(parse_contacts(response.content, file_format)), 2)

    def test_unsupported_formats_are_404(self):
        for name in ["contacts:sample", "contacts:export"]:
            self.assertEqual(self.client.get(reverse(name, args=["exe"])).status_code, 404)

    def test_contact_notes_are_html_escaped(self):
        save_contact(replace(CONTACT, notes="<script>alert('xss')</script>"), "xml")
        response = self.client.get(reverse("contacts:index"))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")

    def test_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("contacts:create"), CONTACT.as_dict()).status_code, 403)
        self.assertEqual(client.post(reverse("contacts:import"), {}).status_code, 403)

    def test_storage_failure_is_presented_as_form_error(self):
        with patch("contacts.views.save_contact", side_effect=PermissionError):
            response = self.client.post(reverse("contacts:create"), {**CONTACT.as_dict(), "file_format": "xml"})
        self.assertContains(response, "Не удалось сохранить файл")

    def test_index_handles_unreadable_directory(self):
        with patch("contacts.views.list_stored_files", side_effect=PermissionError):
            response = self.client.get(reverse("contacts:index"))
        self.assertContains(response, "Не удалось открыть папку")

    def test_download_rejects_post(self):
        self.assertEqual(self.client.post(reverse("contacts:export", args=["xml"])).status_code, 405)
