from django.http import HttpResponse
from django.urls import path


app_name = "contacts"
urlpatterns = [
    path("", lambda request: HttpResponse("Контактная книга"), name="index"),
]
