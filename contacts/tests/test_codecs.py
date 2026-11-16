import json

from django.test import SimpleTestCase, override_settings

from contacts.codecs import InvalidContactFile, parse_contacts, serialize_contacts

from .helpers import CONTACT


class CodecTests(SimpleTestCase):
    def test_round_trip_in_both_formats(self):
        for file_format in ["xml", "json"]:
            with self.subTest(file_format=file_format):
                content = serialize_contacts([CONTACT], file_format)
                self.assertEqual(parse_contacts(content, file_format), [CONTACT])

    def test_xml_escapes_special_characters(self):
        content = serialize_contacts([CONTACT], "xml")
        self.assertIn(b"&amp;", content)
        self.assertIn(b"&lt;", content)

    def test_utf8_bom_is_supported(self):
        for file_format in ["xml", "json"]:
            content = b"\xef\xbb\xbf" + serialize_contacts([CONTACT], file_format)
            self.assertEqual(parse_contacts(content, file_format), [CONTACT])

    def test_non_utf8_file_is_rejected(self):
        with self.assertRaisesMessage(InvalidContactFile, "UTF-8"):
            parse_contacts(b"\xff\xfe", "xml")

    def test_invalid_syntax(self):
        for file_format, content in [("xml", b"<contacts>"), ("json", b'{"version":')]:
            with self.subTest(file_format=file_format), self.assertRaises(InvalidContactFile):
                parse_contacts(content, file_format)

    def test_invalid_roots(self):
        for file_format, content in [("xml", b"<wrong/>"), ("json", b"[]"), ("json", b'{}')]:
            with self.subTest(content=content), self.assertRaises(InvalidContactFile):
                parse_contacts(content, file_format)

    def test_empty_contacts_are_rejected(self):
        for file_format in ["xml", "json"]:
            with self.subTest(file_format=file_format), self.assertRaisesMessage(InvalidContactFile, "не содержит"):
                parse_contacts(serialize_contacts([], file_format), file_format)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesMessage(InvalidContactFile, "Повторяющееся"):
            parse_contacts(b'{"version":1,"version":1,"contacts":[]}', "json")

    def test_json_version_is_strict(self):
        for version in [True, 1.0, "1", 2]:
            content = json.dumps({"version": version, "contacts": [CONTACT.as_dict()]}).encode()
            with self.subTest(version=version), self.assertRaisesMessage(InvalidContactFile, "версия"):
                parse_contacts(content, "json")

    def test_unknown_fields_and_non_string_values_are_rejected(self):
        for changes in [{"unknown": "value"}, {"phone": 79001234567}, {"notes": None}]:
            content = json.dumps({"version": 1, "contacts": [{**CONTACT.as_dict(), **changes}]}).encode()
            with self.subTest(changes=changes), self.assertRaises(InvalidContactFile):
                parse_contacts(content, "json")

    def test_missing_optional_fields_use_defaults(self):
        content = b'{"version":1,"contacts":[{"first_name":"Anna","last_name":"Smith","email":"anna@example.com"}]}'
        contact = parse_contacts(content, "json")[0]
        self.assertEqual(contact.category, "other")
        self.assertEqual(contact.birthday, "")

    def test_invalid_contact_includes_position(self):
        content = json.dumps({"version": 1, "contacts": [CONTACT.as_dict(), {"first_name": "123"}]}).encode()
        with self.assertRaisesMessage(InvalidContactFile, "№2"):
            parse_contacts(content, "json")

    def test_invalid_unicode_is_rejected(self):
        for notes in ["\ud800", "\ufffe", "\x01"]:
            content = json.dumps({"version": 1, "contacts": [{**CONTACT.as_dict(), "notes": notes}]}).encode()
            with self.subTest(notes=repr(notes)), self.assertRaises(InvalidContactFile):
                parse_contacts(content, "json")

    def test_huge_json_integer_is_rejected(self):
        content = b'{"version":' + b"1" * 10000 + b',"contacts":[]}'
        with self.assertRaises(InvalidContactFile):
            parse_contacts(content, "json")

    def test_xml_dtd_and_entities_are_rejected(self):
        payloads = [
            b'<!DOCTYPE contacts [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><contacts version="1"><contact><notes>&xxe;</notes></contact></contacts>',
            b'<!DOCTYPE contacts><contacts version="1"/>',
            b'<!DOCTYPE contacts [<!ENTITY a "ha"><!ENTITY b "&a;&a;">]><contacts version="1">&b;</contacts>',
        ]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaisesMessage(InvalidContactFile, "небезопасный"):
                parse_contacts(payload, "xml")

    def test_invalid_xml_structure(self):
        fragments = [
            "<contact><first_name>A</first_name><first_name>B</first_name></contact>",
            "<contact><first_name><nested/></first_name></contact>",
            "<contact admin='yes'/>",
            "<contact><unknown/></contact>",
            "unexpected text<contact/>",
            "<contact><notes>note</notes>unexpected text</contact>",
        ]
        for fragment in fragments:
            content = f'<contacts version="1">{fragment}</contacts>'.encode()
            with self.subTest(fragment=fragment), self.assertRaises(InvalidContactFile):
                parse_contacts(content, "xml")

    @override_settings(MAX_CONTACTS_PER_FILE=1)
    def test_contact_count_limit(self):
        with self.assertRaisesMessage(InvalidContactFile, "не более 1"):
            parse_contacts(serialize_contacts([CONTACT, CONTACT], "xml"), "xml")

    @override_settings(MAX_CONTACT_FILE_BYTES=4)
    def test_file_size_limit(self):
        with self.assertRaisesMessage(InvalidContactFile, "слишком большой"):
            parse_contacts(b"12345", "xml")

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(InvalidContactFile):
            parse_contacts(b"anything", "html")
        with self.assertRaises(InvalidContactFile):
            serialize_contacts([CONTACT], "html")
