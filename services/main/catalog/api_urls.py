from django.urls import path
from . import api

urlpatterns = [
    path("brands/", api.brand_list, name="brand-list-api"),
    path("brands/<slug:slug>/", api.brand_update, name="brand-update-api"),
]
