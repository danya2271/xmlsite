import re
from dataclasses import fields
from datetime import date

from django import forms

from .domain import CATEGORY_CHOICES, Contact


class ContactForm(forms.Form):
    first_name = forms.CharField(
        label="Имя", max_length=80, widget=forms.TextInput(attrs={"placeholder": "Анна", "autocomplete": "given-name"})
    )
    last_name = forms.CharField(
        label="Фамилия", max_length=80, widget=forms.TextInput(attrs={"placeholder": "Соколова", "autocomplete": "family-name"})
    )
    phone = forms.CharField(
        label="Телефон", required=False, max_length=30,
        widget=forms.TextInput(attrs={"placeholder": "+7 (999) 123-45-67", "type": "tel", "autocomplete": "tel"}),
    )
    email = forms.EmailField(
        label="Электронная почта", required=False, max_length=254,
        widget=forms.EmailInput(attrs={"placeholder": "anna@example.com", "autocomplete": "email"}),
    )
    company = forms.CharField(
        label="Компания", required=False, max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "Название компании", "autocomplete": "organization"}),
    )
    city = forms.CharField(
        label="Город", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Екатеринбург", "autocomplete": "address-level2"}),
    )
    category = forms.ChoiceField(label="Группа", choices=CATEGORY_CHOICES, initial="other")
    birthday = forms.DateField(
        label="День рождения", required=False, input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    notes = forms.CharField(
        label="Заметка", required=False, max_length=1000,
        widget=forms.Textarea(attrs={"placeholder": "Например, где вы познакомились", "rows": 3}),
    )
    storage_target = forms.ChoiceField(
        label="Куда сохранить", choices=(("file", "Файл XML / JSON"), ("database", "База данных SQLite")),
        initial="file", required=False,
    )
    file_format = forms.ChoiceField(
        label="Формат файла", choices=(("xml", "XML"), ("json", "JSON")), initial="xml", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        self.fields["storage_target"].widget.attrs["data-storage-target"] = "true"
        self.fields["file_format"].required = False

    def _clean_name(self, field_name):
        value = self.cleaned_data[field_name]
        if not re.fullmatch(r"[^\W\d_]+(?:[ '\u2019-][^\W\d_]+)*", value):
            raise forms.ValidationError("Используйте буквы, пробел, дефис или апостроф.")
        return value

    def clean_first_name(self):
        return self._clean_name("first_name")

    def clean_last_name(self):
        return self._clean_name("last_name")

    def clean_phone(self):
        value = self.cleaned_data["phone"]
        if value and (
            not re.fullmatch(r"\+?[0-9 ()-]+", value)
            or not 7 <= len(re.sub(r"\D", "", value)) <= 15
        ):
            raise forms.ValidationError("Укажите от 7 до 15 цифр. Допустимы +, пробелы, скобки и дефис.")
        return value

    def clean_birthday(self):
        value = self.cleaned_data["birthday"]
        if value and (value > date.today() or value.year < 1900):
            raise forms.ValidationError("Дата должна быть между 01.01.1900 и сегодняшним днём.")
        return value

    def clean(self):
        cleaned = super().clean()
        if "storage_target" in self.fields:
            cleaned["storage_target"] = cleaned.get("storage_target") or "file"
            if cleaned["storage_target"] == "file" and not cleaned.get("file_format"):
                self.add_error("file_format", "Выберите формат файла: XML или JSON.")
        if not cleaned.get("phone") and not cleaned.get("email"):
            raise forms.ValidationError("Укажите хотя бы один способ связи: телефон или email.")
        for field_name, value in list(cleaned.items()):
            if isinstance(value, str) and any(
                not (
                    character in "\n\r\t"
                    or 0x20 <= ord(character) <= 0xD7FF
                    or 0xE000 <= ord(character) <= 0xFFFD
                    or 0x10000 <= ord(character) <= 0x10FFFF
                )
                for character in value
            ):
                self.add_error(field_name, "Текст содержит недопустимые символы Unicode или управляющие символы.")
        return cleaned

    def to_contact(self):
        if not self.is_valid():
            raise ValueError("Cannot create a contact from an invalid form.")
        values = {field.name: self.cleaned_data[field.name] for field in fields(Contact)}
        values["birthday"] = values["birthday"].isoformat() if values["birthday"] else ""
        return Contact(**values)


class ContactEditForm(ContactForm):
    """The same server-side validation, without storage controls on edit."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["storage_target"]
        del self.fields["file_format"]


class UploadForm(forms.Form):
    file = forms.FileField(
        label="Файл с контактами",
        widget=forms.ClearableFileInput(attrs={"accept": ".xml,.json", "id": "contact-file"}),
    )
