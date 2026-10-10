from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView
from core.views import (
    RegisterView, MeView, DeviceViewSet, RepairRequestViewSet,
    PaymentViewSet, TechnicianViewSet, DashboardSummaryView,
    RepairStatusHistoryViewSet,
)

router = DefaultRouter()
router.register("devices", DeviceViewSet, basename="device")
router.register("repairs", RepairRequestViewSet, basename="repair")
router.register("payments", PaymentViewSet, basename="payment")
router.register("technicians", TechnicianViewSet, basename="technician")
router.register("status-history", RepairStatusHistoryViewSet, basename="status-history")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/logout/", TokenBlacklistView.as_view(), name="token_blacklist"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
