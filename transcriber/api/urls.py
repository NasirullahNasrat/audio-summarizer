from django.urls import path
from . import views

app_name = 'transcriber_api'

urlpatterns = [
    # Upload endpoints
    path('upload/', views.UploadAPIView.as_view(), name='upload'),
    
    # Recording endpoints
    path('recordings/', views.RecordingListAPIView.as_view(), name='recording_list'),
    path('recordings/<int:recording_id>/', views.ResultAPIView.as_view(), name='recording_detail'),
    
    # Status and processing endpoints
    path('status/<int:recording_id>/', views.StatusAPIView.as_view(), name='status'),
    path('result/<int:recording_id>/', views.ResultAPIView.as_view(), name='result'),
    path('regenerate/<int:recording_id>/', views.RegenerateAPIView.as_view(), name='regenerate'),
    
    # Statistics and utility endpoints
    path('stats/', views.StatsAPIView.as_view(), name='stats'),
    path('estimate/', views.EstimateAPIView.as_view(), name='estimate'),
]