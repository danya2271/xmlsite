from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .codecs import InvalidContactFile, serialize_contacts
from .domain import CATEGORY_CHOICES, Contact
from .database import DuplicateContact, find_database_contacts, save_database_contact
from .forms import ContactEditForm, ContactForm, UploadForm
from .models import ContactRecord
from .storage import list_stored_files, read_stored_file, save_contact, save_uploaded_file


def _attachment(content, file_format, filename):
    content_type = "application/xml" if file_format == "xml" else "application/json"
    response = HttpResponse(content, content_type=f"{content_type}; charset=utf-8")
    response["Content-Disposition"] = content_disposition_header(True, f"{filename}.{file_format}")
    return response


@never_cache
@require_GET
def index(request):
    source = request.GET.get("source", "file")
    if source not in {"file", "database"}:
        source = "file"
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")
    file_format = request.GET.get("format", "")
    if category not in dict(CATEGORY_CHOICES):
        category = ""
    if file_format not in {"xml", "json"}:
        file_format = ""
    files, file_errors = [], []
    if source == "database":
        records = find_database_contacts(query=query, category=category)
        rows = [{"contact": record.to_contact(), "record": record} for record in records]
        rows.sort(key=lambda row: (row["contact"].last_name.casefold(), row["contact"].first_name.casefold()))
        total_contacts = ContactRecord.objects.count()
        group_counts = {key: ContactRecord.objects.filter(category=key).count() for key, label in CATEGORY_CHOICES}
    else:
        try:
            files, file_errors = list_stored_files()
        except OSError:
            files, file_errors = [], ["Не удалось открыть папку с контактами. Проверьте права доступа на сервере."]
        rows = [{"contact": contact, "file": stored_file} for stored_file in files for contact in stored_file.contacts]
        total_contacts = len(rows)
        group_counts = {key: sum(row["contact"].category == key for row in rows) for key, label in CATEGORY_CHOICES}
        rows = [row for row in rows if (not category or row["contact"].category == category) and (not file_format or row["file"].file_format == file_format) and (not query or query.casefold() in " ".join(row["contact"].as_dict().values()).casefold())]
        rows.sort(key=lambda row: (row["contact"].last_name.casefold(), row["contact"].first_name.casefold()))
    page = Paginator(rows, 12).get_page(request.GET.get("page"))
    return render(request, "contacts/index.html", {
        "files": files, "file_errors": file_errors, "total_contacts": total_contacts,
        "database_total": ContactRecord.objects.count(),
        "xml_count": sum(stored_file.file_format == "xml" for stored_file in files),
        "json_count": sum(stored_file.file_format == "json" for stored_file in files),
        "groups": [(key, label, group_counts[key]) for key, label in CATEGORY_CHOICES],
        "page_obj": page, "query": query, "category": category, "selected_format": file_format,
        "source": source, "active_page": "contacts",
    })


@never_cache
@require_http_methods(["GET", "POST"])
def create_contact(request):
    form = ContactForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            if form.cleaned_data["storage_target"] == "database":
                save_database_contact(form.to_contact())
            else:
                save_contact(form.to_contact(), form.cleaned_data["file_format"])
        except DuplicateContact as error:
            form.add_error(None, str(error))
        except InvalidContactFile as error:
            form.add_error(None, str(error))
        except OSError:
            form.add_error(None, "Не удалось сохранить файл. Проверьте права доступа к папке на сервере.")
        else:
            if form.cleaned_data["storage_target"] == "database":
                messages.success(request, "Контакт сохранён в базе данных SQLite.")
                return redirect(f"{reverse('contacts:index')}?source=database")
            messages.success(request, "Контакт сохранён. Файл уже доступен в вашей библиотеке.")
            return redirect("contacts:index")
    return render(request, "contacts/create.html", {"form": form, "active_page": "contacts"})


@never_cache
@require_http_methods(["GET", "POST"])
def edit_contact(request, record_id):
    record = get_object_or_404(ContactRecord, pk=record_id)
    form = ContactEditForm(request.POST or None, initial=record.to_contact().as_dict())
    if request.method == "POST" and form.is_valid():
        try:
            save_database_contact(form.to_contact(), instance=record)
        except DuplicateContact as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Изменения сохранены.")
            return redirect(f"{reverse('contacts:index')}?source=database")
    return render(request, "contacts/create.html", {"form": form, "active_page": "contacts", "editing": True, "record": record})


@never_cache
@require_http_methods(["POST"])
def delete_contact(request, record_id):
    record = get_object_or_404(ContactRecord, pk=record_id)
    record.delete()
    messages.success(request, "Контакт удалён из базы данных.")
    return redirect(f"{reverse('contacts:index')}?source=database")


@never_cache
@require_GET
def search_contacts(request):
    query = request.GET.get("q", "").strip()[:100]
    records = find_database_contacts(query)[:50]
    return JsonResponse({"results": [{"id": record.pk, "name": record.to_contact().full_name, "email": record.email, "phone": record.phone, "company": record.company, "city": record.city, "category": record.get_category_display(), "edit_url": reverse("contacts:edit", args=[record.pk])} for record in records]})


@never_cache
@require_http_methods(["GET", "POST"])
def import_contacts(request):
    form = UploadForm(request.POST, request.FILES) if request.method == "POST" else UploadForm()
    if request.method == "POST" and form.is_valid():
        try:
            filename = save_uploaded_file(form.cleaned_data["file"])
            stored_file, _content = read_stored_file(filename)
        except InvalidContactFile as error:
            form.add_error("file", str(error))
        except OSError:
            form.add_error("file", "Не удалось сохранить файл. Проверьте права доступа к папке на сервере.")
        else:
            messages.success(request, f"Импорт завершён. Добавлено контактов: {len(stored_file.contacts)}.")
            return redirect("contacts:index")
    return render(request, "contacts/import.html", {"form": form, "active_page": "import"})


@never_cache
@require_GET
def download_file(request, filename):
    try:
        stored_file, content = read_stored_file(filename)
    except (OSError, InvalidContactFile) as error:
        raise Http404("Файл не найден или повреждён.") from error
    file_format = request.GET.get("format", stored_file.file_format)
    if file_format not in {"xml", "json"}:
        raise Http404("Неизвестный формат.")
    if file_format != stored_file.file_format:
        content = serialize_contacts(stored_file.contacts, file_format)
    return _attachment(content, file_format, f"contacts-{filename.split('.')[0]}")


@never_cache
@require_GET
def export_contacts(request, file_format):
    if file_format not in {"xml", "json"}:
        raise Http404("Неизвестный формат.")
    try:
        files, errors = list_stored_files()
    except OSError:
        messages.error(request, "Не удалось прочитать папку с контактами.")
        return redirect("contacts:index")
    contacts = [contact for stored_file in files for contact in stored_file.contacts]
    if not contacts:
        messages.info(request, "Пока нечего экспортировать. Добавьте контакт или загрузите файл.")
        return redirect("contacts:index")
    if errors:
        messages.error(request, "Экспорт отменён: есть повреждённые файлы. Проверьте библиотеку, чтобы не потерять данные.")
        return redirect("contacts:index")
    content = serialize_contacts(contacts, file_format)
    if len(contacts) > settings.MAX_CONTACTS_PER_FILE or len(content) > settings.MAX_CONTACT_FILE_BYTES:
        messages.error(request, "Данные не помещаются в один файл (500 контактов / 1 МБ). Скачайте исходные файлы по отдельности.")
        return redirect("contacts:index")
    return _attachment(content, file_format, "all-contacts")


@require_GET
def sample_file(request, file_format):
    if file_format not in {"xml", "json"}:
        raise Http404("Неизвестный формат.")
    contacts = [
        Contact("Анна", "Соколова", "+7 (900) 123-45-67", "anna@example.com", "Студия Форма", "Екатеринбург", "work", "1998-04-12", "Обсудить новый проект."),
        Contact("Михаил", "Волков", "+7 (900) 765-43-21", "mikhail@example.com", "", "Казань", "friends", "1997-09-25", "Познакомились на конференции."),
    ]
    return _attachment(serialize_contacts(contacts, file_format), file_format, "example-contacts")
