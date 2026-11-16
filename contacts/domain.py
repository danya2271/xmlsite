from dataclasses import asdict, dataclass


CATEGORY_CHOICES = (
    ("work", "Работа"),
    ("friends", "Друзья"),
    ("family", "Семья"),
    ("other", "Другое"),
)


@dataclass(frozen=True)
class Contact:
    first_name: str
    last_name: str
    phone: str = ""
    email: str = ""
    company: str = ""
    city: str = ""
    category: str = "other"
    birthday: str = ""
    notes: str = ""

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def initials(self):
        return f"{self.first_name[0]}{self.last_name[0]}".upper()

    @property
    def category_label(self):
        return dict(CATEGORY_CHOICES)[self.category]

    def as_dict(self):
        return asdict(self)
