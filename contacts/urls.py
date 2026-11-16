from django.urls import path

from . import views


app_name = "contacts"
urlpatterns = [
    path("", views.index, name="index"),
    path("contacts/new/", views.create_contact, name="create"),
    path("import/", views.import_contacts, name="import"),
    path("files/<str:filename>/", views.download_file, name="download"),
    path("export/<str:file_format>/", views.export_contacts, name="export"),
    path("examples/<str:file_format>/", views.sample_file, name="sample"),
]
