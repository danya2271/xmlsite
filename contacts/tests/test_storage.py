from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from contacts.codecs import InvalidContactFile, serialize_contacts
from contacts.storage import list_stored_files, read_stored_file, save_contact, save_uploaded_file

from .helpers import CONTACT, StorageTestCase


class StorageTests(StorageTestCase):
    def test_missing_directory_is_created_and_empty(self):
        self.assertEqual(list_stored_files(), ([], []))
        self.assertTrue(self.storage.is_dir())

    def test_save_and_read_contact(self):
        filename = save_contact(CONTACT, "xml")
        self.assertRegex(filename, r"^[a-f0-9]{32}\.xml$")
        stored_file, content = read_stored_file(filename)
        self.assertEqual(stored_file.contacts, (CONTACT,))
        self.assertGreater(stored_file.size, 0)
        self.assertIn(b"<contacts", content)

    def test_upload_uses_generated_name(self):
        upload = SimpleUploadedFile("../../dangerous.name.XML", serialize_contacts([CONTACT], "xml"))
        filename = save_uploaded_file(upload)
        self.assertRegex(filename, r"^[a-f0-9]{32}\.xml$")
        self.assertNotIn("dangerous", filename)
        self.assertEqual(len(list(self.storage.iterdir())), 1)

    def test_invalid_upload_is_deleted(self):
        upload = SimpleUploadedFile("contacts.xml", b"<not-valid>")
        with self.assertRaises(InvalidContactFile):
            save_uploaded_file(upload)
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_invalid_second_contact_does_not_partially_import(self):
        content = b'{"version":1,"contacts":[{"first_name":"Anna","last_name":"Smith","email":"a@example.com"},{}]}'
        with self.assertRaises(InvalidContactFile):
            save_uploaded_file(SimpleUploadedFile("contacts.json", content))
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_wrong_extension_is_rejected(self):
        upload = SimpleUploadedFile("contacts.exe", serialize_contacts([CONTACT], "xml"))
        with self.assertRaises(InvalidContactFile):
            save_uploaded_file(upload)
        self.assertFalse(self.storage.exists())

    @override_settings(MAX_CONTACT_FILE_BYTES=10)
    def test_oversized_upload_is_rejected(self):
        with self.assertRaisesMessage(InvalidContactFile, "слишком большой"):
            save_uploaded_file(SimpleUploadedFile("contacts.xml", b"x" * 11))

    def test_existing_files_are_all_read(self):
        self.storage.mkdir()
        (self.storage / "old-contacts.XML").write_bytes(serialize_contacts([CONTACT], "xml"))
        (self.storage / "other.json").write_bytes(serialize_contacts([CONTACT], "json"))
        files, errors = list_stored_files()
        self.assertEqual(len(files), 2)
        self.assertEqual(errors, [])

    def test_invalid_existing_file_is_reported_without_hiding_valid_files(self):
        save_contact(CONTACT, "xml")
        (self.storage / "broken.json").write_text("broken")
        (self.storage / "notes.txt").write_text("ignore")
        files, errors = list_stored_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(len(errors), 1)

    def test_path_traversal_is_rejected(self):
        for filename in ["../outside.xml", "/tmp/outside.xml", "..\\outside.xml", ".hidden.xml"]:
            with self.subTest(filename=filename), self.assertRaises(FileNotFoundError):
                read_stored_file(filename)

    def test_symlinks_are_not_read(self):
        self.storage.mkdir()
        outside = self.storage.parent / "outside.xml"
        outside.write_bytes(serialize_contacts([CONTACT], "xml"))
        (self.storage / "linked.xml").symlink_to(outside)
        with self.assertRaises(FileNotFoundError):
            read_stored_file("linked.xml")

    def test_failed_atomic_rename_cleans_temporary_file(self):
        with patch("contacts.storage.Path.replace", side_effect=OSError("read-only")):
            with self.assertRaises(OSError):
                save_contact(CONTACT, "xml")
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_same_upload_twice_gets_unique_filenames(self):
        first = save_contact(CONTACT, "json")
        second = save_contact(CONTACT, "json")
        self.assertNotEqual(first, second)
