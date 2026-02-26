from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('generate/', views.create_notice, name='create_notice'),
    path('download/', views.download_pdf, name='download_pdf'),
    path('download-word/', views.download_word, name='download_word'),
    path('history/', views.notice_history, name='notice_history'),
    path('view/<int:id>/', views.view_notice, name='view_notice'),
    path('signup/', views.signup, name='signup'),
]