import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from django.conf import settings

from .codecs import InvalidContactFile, parse_contacts, serialize_contacts
from .domain import Contact


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredFile:
    name: str
    file_format: str
    size: int
    modified: datetime
    contacts: tuple[Contact, ...]


def storage_directory():
    directory = Path(settings.CONTACTS_STORAGE_DIR)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def _save_content(content, file_format):
    if len(content) > settings.MAX_CONTACT_FILE_BYTES:
        raise InvalidContactFile("Файл слишком большой. Максимальный размер — 1 МБ.")
    directory = storage_directory()
    filename = f"{uuid4().hex}.{file_format}"
    temporary_path = directory / f".{uuid4().hex}.tmp"
    destination = directory / filename
    try:
        with temporary_path.open("xb") as target:
            temporary_path.chmod(0o600)
            target.write(content)
        parse_contacts(content, file_format)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return filename


def save_contact(contact, file_format):
    return _save_content(serialize_contacts([contact], file_format), file_format)


def save_uploaded_file(uploaded_file):
    file_format = Path(uploaded_file.name).suffix.lower().lstrip(".")
    if file_format not in {"xml", "json"}:
        raise InvalidContactFile("Выберите файл с расширением .xml или .json.")
    if uploaded_file.size > settings.MAX_CONTACT_FILE_BYTES:
        raise InvalidContactFile("Файл слишком большой. Максимальный размер — 1 МБ.")
    content = bytearray()
    for chunk in uploaded_file.chunks():
        content.extend(chunk)
        if len(content) > settings.MAX_CONTACT_FILE_BYTES:
            raise InvalidContactFile("Файл слишком большой. Максимальный размер — 1 МБ.")
    return _save_content(bytes(content), file_format)


def read_stored_file(filename):
    if (
        Path(filename).name != filename
        or "\\" in filename
        or filename.startswith(".")
        or Path(filename).suffix.lower() not in {".xml", ".json"}
    ):
        raise FileNotFoundError("Unknown contact file.")
    path = storage_directory() / filename
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError("Unknown contact file.")
    with path.open("rb") as source:
        content = source.read(settings.MAX_CONTACT_FILE_BYTES + 1)
    file_format = path.suffix[1:].lower()
    contacts = parse_contacts(content, file_format)
    metadata = path.stat()
    return StoredFile(
        name=filename,
        file_format=file_format,
        size=metadata.st_size,
        modified=datetime.fromtimestamp(metadata.st_mtime, tz=timezone.utc),
        contacts=tuple(contacts),
    ), content


def list_stored_files():
    files = []
    errors = []
    directory = storage_directory()
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".xml", ".json"}:
            continue
        try:
            stored_file, _content = read_stored_file(path.name)
            files.append(stored_file)
        except (OSError, InvalidContactFile):
            logger.warning("Cannot read contact file %s", path.name)
            errors.append(f"Файл «{path.name}» повреждён, недоступен или имеет небезопасное имя и пропущен.")
    files.sort(key=lambda stored_file: (stored_file.modified, stored_file.name), reverse=True)
    return files, errors
