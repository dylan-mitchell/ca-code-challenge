from django.urls import path

from accounts import views


urlpatterns = [
    path("api/login/", views.login, name="login"),
    path("api/tokens/introspect/", views.introspect, name="introspect"),
]
