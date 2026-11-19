import hashlib
import json
import re
import unicodedata
from dataclasses import fields

from django.core.exceptions import ValidationError
from django.db import models

from .domain import CATEGORY_CHOICES, Contact
from .forms import ContactEditForm


def normalize_text(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class ContactRecord(models.Model):
    first_name = models.CharField("Имя", max_length=80)
    last_name = models.CharField("Фамилия", max_length=80)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    email = models.EmailField("Электронная почта", max_length=254, blank=True)
    company = models.CharField("Компания", max_length=120, blank=True)
    city = models.CharField("Город", max_length=100, blank=True)
    category = models.CharField("Группа", max_length=10, choices=CATEGORY_CHOICES, default="other")
    birthday = models.DateField("День рождения", blank=True, null=True)
    notes = models.TextField("Заметка", max_length=1000, blank=True)
    duplicate_key = models.CharField(max_length=64, unique=True, editable=False)
    searchable_text = models.TextField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "pk")
        verbose_name = "Контакт"
        verbose_name_plural = "Контакты"

    def __str__(self):
        return self.to_contact().full_name

    def to_contact(self):
        values = {field.name: getattr(self, field.name) for field in fields(Contact)}
        values["birthday"] = self.birthday.isoformat() if self.birthday else ""
        return Contact(**values)

    def refresh_derived_fields(self):
        contact = self.to_contact()
        normalized = {key: normalize_text(value) for key, value in contact.as_dict().items()}
        normalized["phone"] = re.sub(r"\D", "", contact.phone)
        self.duplicate_key = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        # Python casefold handles Cyrillic; SQLite's built-in LIKE/LOWER does not.
        self.searchable_text = normalize_text(
            " ".join([*contact.as_dict().values(), contact.category_label])
        )

    def clean(self):
        super().clean()
        form = ContactEditForm(self.to_contact().as_dict())
        if not form.is_valid():
            raise ValidationError(form.errors.as_data())

    def save(self, *args, **kwargs):
        # Validate typed fields before converting the model to the domain object.
        self.clean_fields(exclude={"duplicate_key", "searchable_text"})
        self.clean()
        self.refresh_derived_fields()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "duplicate_key", "searchable_text", "updated_at"
            }
        super().save(*args, **kwargs)
