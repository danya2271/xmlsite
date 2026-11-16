import re
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
    file_format = forms.ChoiceField(
        label="Формат файла", choices=(("xml", "XML"), ("json", "JSON")), initial="xml"
    )

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
        if not cleaned.get("phone") and not cleaned.get("email"):
            raise forms.ValidationError("Укажите хотя бы один способ связи: телефон или email.")
        for field_name, value in cleaned.items():
            if isinstance(value, str) and any(
                ord(character) < 32 and character not in "\n\r\t" for character in value
            ):
                self.add_error(field_name, "Текст содержит недопустимые управляющие символы.")
        return cleaned

    def to_contact(self):
        if not self.is_valid():
            raise ValueError("Cannot create a contact from an invalid form.")
        values = {key: value for key, value in self.cleaned_data.items() if key != "file_format"}
        values["birthday"] = values["birthday"].isoformat() if values["birthday"] else ""
        return Contact(**values)


class UploadForm(forms.Form):
    file = forms.FileField(
        label="Файл с контактами",
        widget=forms.ClearableFileInput(attrs={"accept": ".xml,.json", "id": "contact-file"}),
    )
