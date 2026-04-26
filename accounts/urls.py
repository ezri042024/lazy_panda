from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import RegisterAPIView, CurrentUserAPIView


urlpatterns = [
    path("register/", RegisterAPIView.as_view(), name="api_register"),
    path("login/", TokenObtainPairView.as_view(), name="api_login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="api_token_refresh"),
    path("me/", CurrentUserAPIView.as_view(), name="api_current_user"),
]