from django.urls import path
from . import views

app_name = 'transcriber'

urlpatterns = [
    # Home and upload
    path('', views.HomeView.as_view(), name='home'),
    path('upload/', views.AudioUploadView.as_view(), name='upload'),
    
    # Recording management
    path('recordings/', views.RecordingListView.as_view(), name='recording_list'),
    path('recordings/<int:pk>/', views.RecordingDetailView.as_view(), name='recording_detail'),
    path('recordings/<int:pk>/regenerate/', views.RegenerateSummaryView.as_view(), name='regenerate_summary'),
    
    # Download endpoints
    path('recordings/<int:pk>/download/transcription/', views.download_transcription, name='download_transcription'),
    path('recordings/<int:pk>/download/summary/', views.download_summary, name='download_summary'),
    
    # Status and statistics
    path('recordings/<int:pk>/status/', views.RecordingStatusView.as_view(), name='recording_status'),
    path('statistics/', views.get_statistics, name='statistics'),
    path('export/csv/', views.export_recordings_csv, name='export_csv'),
]