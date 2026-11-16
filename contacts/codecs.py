import json
from dataclasses import fields
from xml.etree import ElementTree

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException
from django.conf import settings

from .domain import Contact
from .forms import ContactForm


class InvalidContactFile(ValueError):
    pass


CONTACT_FIELDS = {field.name for field in fields(Contact)}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidContactFile(f"Повторяющееся поле JSON: {key}.")
        result[key] = value
    return result


def _parse_json(text):
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except InvalidContactFile:
        raise
    except (ValueError, RecursionError) as error:
        raise InvalidContactFile("Некорректный JSON. Проверьте синтаксис файла.") from error
    if not isinstance(payload, dict) or set(payload) != {"version", "contacts"}:
        raise InvalidContactFile("JSON должен содержать только поля version и contacts.")
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise InvalidContactFile("Поддерживается только версия формата 1.")
    if not isinstance(payload["contacts"], list):
        raise InvalidContactFile("Поле contacts должно быть массивом.")
    return payload["contacts"]


def _parse_xml(text):
    try:
        root = SafeElementTree.fromstring(
            text, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (ElementTree.ParseError, DefusedXmlException, ValueError, RecursionError) as error:
        raise InvalidContactFile("Некорректный или небезопасный XML. DTD и сущности запрещены.") from error
    if root.tag != "contacts" or root.attrib != {"version": "1"}:
        raise InvalidContactFile('Корневой элемент XML должен быть <contacts version="1">.')
    if root.text and root.text.strip():
        raise InvalidContactFile("Текст вне элементов контакта недопустим.")
    records = []
    for element in root:
        if element.tag != "contact" or element.attrib:
            raise InvalidContactFile("Внутри contacts допустимы только элементы contact без атрибутов.")
        if (element.text and element.text.strip()) or (element.tail and element.tail.strip()):
            raise InvalidContactFile("Текст вне полей контакта недопустим.")
        record = {}
        for child in element:
            if child.tag not in CONTACT_FIELDS or child.tag in record or child.attrib or len(child):
                raise InvalidContactFile("XML содержит неизвестное, повторяющееся или вложенное поле.")
            if child.tail and child.tail.strip():
                raise InvalidContactFile("Текст между полями контакта недопустим.")
            record[child.tag] = child.text or ""
        records.append(record)
    return records


def parse_contacts(content, file_format):
    if len(content) > settings.MAX_CONTACT_FILE_BYTES:
        raise InvalidContactFile("Файл слишком большой. Максимальный размер — 1 МБ.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InvalidContactFile("Сохраните файл в кодировке UTF-8.") from error
    if file_format == "xml":
        records = _parse_xml(text)
    elif file_format == "json":
        records = _parse_json(text)
    else:
        raise InvalidContactFile("Поддерживаются только файлы .xml и .json.")
    if not records:
        raise InvalidContactFile("Файл не содержит контактов.")
    if len(records) > settings.MAX_CONTACTS_PER_FILE:
        raise InvalidContactFile(f"В одном файле допускается не более {settings.MAX_CONTACTS_PER_FILE} контактов.")
    contacts = []
    for position, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) - CONTACT_FIELDS:
            raise InvalidContactFile(f"Контакт №{position}: неверная структура или неизвестные поля.")
        if any(not isinstance(value, str) for value in record.values()):
            raise InvalidContactFile(f"Контакт №{position}: все значения должны быть строками.")
        form = ContactForm(data={**record, "category": record.get("category", "other"), "file_format": file_format})
        if not form.is_valid():
            details = "; ".join(
                f"{form.fields[key].label if key in form.fields else 'Данные'}: {' '.join(errors)}"
                for key, errors in form.errors.items()
            )
            raise InvalidContactFile(f"Контакт №{position}: {details}")
        contacts.append(form.to_contact())
    return contacts


def serialize_contacts(contacts, file_format):
    records = [contact.as_dict() for contact in contacts]
    if file_format == "json":
        return (json.dumps({"version": 1, "contacts": records}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if file_format != "xml":
        raise InvalidContactFile("Поддерживаются только форматы XML и JSON.")
    root = ElementTree.Element("contacts", version="1")
    for record in records:
        element = ElementTree.SubElement(root, "contact")
        for name, value in record.items():
            ElementTree.SubElement(element, name).text = value
    ElementTree.indent(root, space="  ")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
