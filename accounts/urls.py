from django.urls import path

from .views import OperadorLoginView, OperadorLogoutView

app_name = "accounts"

urlpatterns = [
    path("login/", OperadorLoginView.as_view(), name="login"),
    path("logout/", OperadorLogoutView.as_view(), name="logout"),
]
