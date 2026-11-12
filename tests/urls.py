from django.urls import include, path

urlpatterns = [
    path("courses/api/", include("stapel_courses.urls")),
]
