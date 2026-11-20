from django.urls import include, path

urlpatterns = [
    path("api/", include("catalog.api_urls")),
    path("", include("catalog.page_urls")),
]
