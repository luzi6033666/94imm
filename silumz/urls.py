"""silumz URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.urls import re_path
from images import views

urlpatterns = [
    re_path(r'^$', views.index),
    re_path(r'^article/(?P<i_id>\d+)/$', views.page, name='article'),
    re_path(r'^tag/(?P<tid>\d+)/$', views.tag, name='tag'),
    re_path(r'^type/(?P<typeid>\d+)/$', views.type, name='type'),
    re_path(r'^search/$', views.search),
    re_path(r'^get_video/$', views.getVideo),
    re_path(r'^video/$', views.pVideo),
    re_path(r'^mvideo/$', views.mVideo),
    re_path(r'^tag/$', views.HotTag),
    re_path(r'^sort/(?P<method>\w+)/$', views.SortBy, name='sort'),
]
