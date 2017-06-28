from django.conf.urls import include, url

from api import views as api_views
from rest_framework_nested import routers

router = routers.DefaultRouter()
router.register(r'users', api_views.UserViewSet)
router.register(r'studies', api_views.StudyViewSet)
router.register(r'demographics', api_views.DemographicDataViewSet)
router.register(r'children', api_views.ChildViewSet)
router.register(r'responses', api_views.ResponseViewSet)
router.register(r'organizations', api_views.OrganizationViewSet)

user_router = routers.NestedSimpleRouter(router, r'users', lookup='user')
user_router.register(r'demographics', api_views.DemographicDataViewSet, base_name='user-demographics')
user_router.register(r'organizations', api_views.OrganizationViewSet, base_name='user-organizations')
user_router.register(r'children', api_views.ChildViewSet, base_name='user-children')

study_router = routers.NestedSimpleRouter(router, r'studies', lookup='study')
study_router.register(r'organizations', api_views.OrganizationViewSet, base_name='study-organizations')
study_router.register(r'responses', api_views.ResponseViewSet, base_name='study-responses')

child_router = routers.NestedSimpleRouter(router, r'children', lookup='child')
child_router.register(r'users', api_views.UserViewSet, base_name='child-users')

response_router = routers.NestedSimpleRouter(router, r'responses', lookup='response')
response_router.register(r'studies', api_views.StudyViewSet, base_name='response-studies')
response_router.register(r'users', api_views.UserViewSet, base_name='response-users')
response_router.register(r'children', api_views.ChildViewSet, base_name='response-children')


urlpatterns = [
    url(r'^(?P<version>(v1|v2))/', include(user_router.urls)),
    url(r'^(?P<version>(v1|v2))/', include(study_router.urls)),
    url(r'^(?P<version>(v1|v2))/', include(child_router.urls)),
    url(r'^(?P<version>(v1|v2))/', include(response_router.urls)),
    url(r'^(?P<version>(v1|v2))/', include(router.urls)),
]
