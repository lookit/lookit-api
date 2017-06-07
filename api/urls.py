from django.conf.urls import include, url
from rest_framework.routers import DefaultRouter

from api import views as api_views

router = DefaultRouter()
router.register(r'users', api_views.UserViewSet)
router.register(r'studies', api_views.StudyViewSet)

router.register(r'profiles/(?P<profile_id>.*?)/demographics',
                api_views.ProfileDemographicsViewSet,
                base_name='profile-demographics'
                )
router.register(r'profiles', api_views.ProfileViewSet)

urlpatterns = [
    url(r'^(?P<version>(v1|v2))/', include(router.urls))
]
