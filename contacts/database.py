from datetime import date

from django.db import IntegrityError, transaction

from .models import ContactRecord, normalize_text


class DuplicateContact(ValueError):
    pass


def save_database_contact(contact, instance=None):
    record = instance if instance is not None else ContactRecord()
    for field, value in contact.as_dict().items():
        setattr(record, field, date.fromisoformat(value) if field == "birthday" and value else (
            None if field == "birthday" else value
        ))
    record.refresh_derived_fields()
    existing = ContactRecord.objects.filter(duplicate_key=record.duplicate_key)
    if record.pk:
        existing = existing.exclude(pk=record.pk)
    if existing.exists():
        raise DuplicateContact("Такая запись уже присутствует в базе данных. Дубликат не сохранён.")
    try:
        with transaction.atomic():
            record.save()
    except IntegrityError as error:
        # The UNIQUE constraint also protects simultaneous duplicate requests.
        if existing.exists():
            raise DuplicateContact("Такая запись уже присутствует в базе данных. Дубликат не сохранён.") from error
        raise
    return record


def find_database_contacts(query="", category=""):
    records = ContactRecord.objects.all()
    if category:
        records = records.filter(category=category)
    if query:
        records = records.filter(searchable_text__contains=normalize_text(query))
    return records
