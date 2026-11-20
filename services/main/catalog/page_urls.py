from django.urls import path

from . import page_views

app_name = "catalog"

urlpatterns = [
    path("", page_views.home, name="home"),
    path("brand/", page_views.brand_list, name="brand-list"),
    path("brand/<slug:slug>/", page_views.brand_detail, name="brand-detail"),
    path("review/<slug:slug>/", page_views.review_detail, name="review-detail"),
]
