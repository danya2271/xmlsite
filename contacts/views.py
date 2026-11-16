from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .codecs import InvalidContactFile, serialize_contacts
from .domain import CATEGORY_CHOICES, Contact
from .forms import ContactForm, UploadForm
from .storage import list_stored_files, read_stored_file, save_contact, save_uploaded_file


def _attachment(content, file_format, filename):
    content_type = "application/xml" if file_format == "xml" else "application/json"
    response = HttpResponse(content, content_type=f"{content_type}; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.{file_format}"'
    return response


@never_cache
@require_GET
def index(request):
    try:
        files, file_errors = list_stored_files()
    except OSError:
        files, file_errors = [], ["Не удалось открыть папку с контактами. Проверьте права доступа на сервере."]
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")
    file_format = request.GET.get("format", "")
    if category not in dict(CATEGORY_CHOICES):
        category = ""
    if file_format not in {"xml", "json"}:
        file_format = ""
    rows = [{"contact": contact, "file": stored_file} for stored_file in files for contact in stored_file.contacts]
    total_contacts = len(rows)
    group_counts = {key: sum(row["contact"].category == key for row in rows) for key, label in CATEGORY_CHOICES}
    filtered = [
        row for row in rows
        if (not category or row["contact"].category == category)
        and (not file_format or row["file"].file_format == file_format)
        and (not query or query.casefold() in " ".join(row["contact"].as_dict().values()).casefold())
    ]
    filtered.sort(key=lambda row: (row["contact"].last_name.casefold(), row["contact"].first_name.casefold()))
    page = Paginator(filtered, 12).get_page(request.GET.get("page"))
    return render(request, "contacts/index.html", {
        "files": files,
        "file_errors": file_errors,
        "total_contacts": total_contacts,
        "xml_count": sum(stored_file.file_format == "xml" for stored_file in files),
        "json_count": sum(stored_file.file_format == "json" for stored_file in files),
        "groups": [(key, label, group_counts[key]) for key, label in CATEGORY_CHOICES],
        "page_obj": page,
        "query": query,
        "category": category,
        "selected_format": file_format,
        "active_page": "contacts",
    })


@never_cache
@require_http_methods(["GET", "POST"])
def create_contact(request):
    form = ContactForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            save_contact(form.to_contact(), form.cleaned_data["file_format"])
        except InvalidContactFile as error:
            form.add_error(None, str(error))
        except OSError:
            form.add_error(None, "Не удалось сохранить файл. Проверьте права доступа к папке на сервере.")
        else:
            messages.success(request, "Контакт сохранён. Файл уже доступен в вашей библиотеке.")
            return redirect("contacts:index")
    return render(request, "contacts/create.html", {"form": form, "active_page": "contacts"})


@never_cache
@require_http_methods(["GET", "POST"])
def import_contacts(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            filename = save_uploaded_file(form.cleaned_data["file"])
            stored_file, content = read_stored_file(filename)
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
