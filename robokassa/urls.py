from django.conf.urls import patterns, url
from django.views.decorators.csrf import csrf_exempt
from robokassa import views

urlpatterns = patterns('',
    url(
          r'^result/$',
          csrf_exempt(views.ResultResponseView.as_view()),
          name='result'
    ),
    url(
          r'^success/$',
          csrf_exempt(views.SuccessResponseView.as_view()),
          name='success'
    ),
    url(
          r'^fail/$',
          csrf_exempt(views.FailResponseView.as_view()),
          name='fail'
    ),
    url(
          r'^redirect/$',
          csrf_exempt(views.RedirectView.as_view()),
          name='redirect'
    ),
)
