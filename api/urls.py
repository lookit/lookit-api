from django.conf.urls import include, url
from rest_framework.routers import DefaultRouter

from api import views as api_views

router = DefaultRouter()
router.register(r'users', api_views.ParticipantViewSet)

urlpatterns = [
    url(r'^(?P<version>(v1|v2))/', include(router.urls))
]
