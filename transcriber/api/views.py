from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from celery import current_app
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from datetime import datetime, timedelta

from ..models import AudioRecording
from ..forms import AudioUploadForm
from ..tasks import transcribe_audio_task, regenerate_summary
from .serializers import (
    AudioRecordingSerializer,
    AudioUploadSerializer,
    StatusSerializer,
    RegenerateSerializer,
    StatsSerializer,
    EstimateSerializer,
)


class UploadAPIView(generics.CreateAPIView):
    """
    API endpoint for uploading audio files.
    
    POST /api/upload/
    """
    queryset = AudioRecording.objects.all()
    serializer_class = AudioUploadSerializer
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create recording instance
        recording = serializer.save()
        
        # Start transcription (async only for Redis broker, otherwise sync fallback)
        broker_url = str(current_app.conf.broker_url or '')
        task_id = None
        if broker_url.startswith('redis://'):
            task = transcribe_audio_task.delay(recording.id)
            task_id = task.id
            recording.task_id = task.id
            recording.save(update_fields=['task_id'])
        else:
            transcribe_audio_task.run(recording.id)
            recording.refresh_from_db()
            if recording.status in ['pending', 'transcribing', 'summarizing']:
                recording.status = 'failed'
                recording.error_message = 'Processing did not finalize during synchronous execution.'
                recording.save(update_fields=['status', 'error_message'])
        
        # Return response with recording data
        response_serializer = AudioRecordingSerializer(recording)
        headers = self.get_success_headers(response_serializer.data)
        
        return Response(
            {
                'message': 'Audio uploaded successfully. Processing started.',
                'recording': response_serializer.data,
                'task_id': task_id,
            },
            status=status.HTTP_201_CREATED,
            headers=headers
        )


class StatusAPIView(generics.RetrieveAPIView):
    """
    API endpoint for getting recording status.
    
    GET /api/status/{recording_id}/
    """
    queryset = AudioRecording.objects.all()
    serializer_class = StatusSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_object(self):
        recording_id = self.kwargs.get('recording_id')
        return get_object_or_404(AudioRecording, id=recording_id)
    
    def retrieve(self, request, *args, **kwargs):
        recording = self.get_object()
        serializer = self.get_serializer(recording)
        
        # Add task status if available
        data = serializer.data
        if recording.task_id:
            from celery.result import AsyncResult
            task_result = AsyncResult(recording.task_id)
            data['task_status'] = task_result.status
            data['task_result'] = task_result.result if task_result.ready() else None
        
        return Response(data)


class ResultAPIView(generics.RetrieveAPIView):
    """
    API endpoint for getting recording results.
    
    GET /api/result/{recording_id}/
    """
    queryset = AudioRecording.objects.all()
    serializer_class = AudioRecordingSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_object(self):
        recording_id = self.kwargs.get('recording_id')
        return get_object_or_404(AudioRecording, id=recording_id)


class RegenerateAPIView(generics.UpdateAPIView):
    """
    API endpoint for regenerating summary.
    
    POST /api/regenerate/{recording_id}/
    """
    queryset = AudioRecording.objects.all()
    serializer_class = RegenerateSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_object(self):
        recording_id = self.kwargs.get('recording_id')
        return get_object_or_404(AudioRecording, id=recording_id)
    
    def update(self, request, *args, **kwargs):
        recording = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        summary_style = serializer.validated_data.get('summary_style')
        api_provider = serializer.validated_data.get('api_provider')
        
        # Update provider if changed
        if api_provider and api_provider != recording.api_provider:
            recording.api_provider = api_provider
            recording.save(update_fields=['api_provider'])
        
        # Trigger regeneration (async only for Redis broker, otherwise sync fallback)
        broker_url = str(current_app.conf.broker_url or '')
        task_id = None
        if broker_url.startswith('redis://'):
            task = regenerate_summary.delay(recording.id, summary_style, api_provider)
            task_id = task.id
            recording.task_id = task.id
            recording.status = 'summarizing'
            recording.save(update_fields=['task_id', 'status'])
        else:
            regenerate_summary.run(recording.id, summary_style, api_provider)
            recording.refresh_from_db()
            if recording.status in ['pending', 'transcribing', 'summarizing']:
                recording.status = 'failed'
                recording.error_message = 'Regeneration did not finalize during synchronous execution.'
                recording.save(update_fields=['status', 'error_message'])
        
        return Response({
            'message': 'Summary regeneration started.',
            'recording_id': recording.id,
            'task_id': task_id,
            'summary_style': summary_style,
            'api_provider': api_provider or recording.api_provider,
        })


class StatsAPIView(APIView):
    """
    API endpoint for getting statistics.
    
    GET /api/stats/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Get date range from query params
        days = int(request.query_params.get('days', 30))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Get recordings in date range
        recordings = AudioRecording.objects.filter(
            created_at__range=[start_date, end_date]
        )
        
        # Calculate statistics
        total_recordings = recordings.count()
        completed_recordings = recordings.filter(status='completed').count()
        
        total_cost = recordings.aggregate(
            total=Sum('cost_estimate')
        )['total'] or 0
        
        avg_processing_time = recordings.filter(
            processing_time__isnull=False
        ).aggregate(
            avg=Avg('processing_time')
        )['avg'] or 0
        
        # Token usage totals
        total_tokens = 0
        for recording in recordings:
            tokens = recording.token_usage.get('total_tokens', 0)
            total_tokens += tokens
        
        # Provider distribution
        provider_stats = []
        for provider_code, provider_name in AudioRecording.API_PROVIDER_CHOICES:
            provider_recordings = recordings.filter(api_provider=provider_code)
            provider_count = provider_recordings.count()
            provider_cost = provider_recordings.aggregate(
                total=Sum('cost_estimate')
            )['total'] or 0
            
            if provider_count > 0:
                provider_stats.append({
                    'provider': provider_name,
                    'count': provider_count,
                    'cost': float(provider_cost),
                    'percentage': (provider_count / total_recordings * 100) if total_recordings > 0 else 0,
                })
        
        # Style distribution
        style_stats = []
        for style_code, style_name in AudioRecording.SUMMARY_STYLE_CHOICES:
            style_count = recordings.filter(summary_style=style_code).count()
            if style_count > 0:
                style_stats.append({
                    'style': style_name,
                    'count': style_count,
                    'percentage': (style_count / total_recordings * 100) if total_recordings > 0 else 0,
                })
        
        # Daily statistics
        daily_stats = []
        current_date = start_date.date()
        
        while current_date <= end_date.date():
            day_recordings = recordings.filter(created_at__date=current_date)
            day_count = day_recordings.count()
            day_cost = day_recordings.aggregate(
                total=Sum('cost_estimate')
            )['total'] or 0
            
            daily_stats.append({
                'date': current_date.isoformat(),
                'count': day_count,
                'cost': float(day_cost),
            })
            
            current_date += timedelta(days=1)
        
        data = {
            'total_recordings': total_recordings,
            'completed_recordings': completed_recordings,
            'total_cost': float(total_cost),
            'avg_processing_time': float(avg_processing_time),
            'total_tokens': total_tokens,
            'provider_stats': provider_stats,
            'style_stats': style_stats,
            'daily_stats': daily_stats,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days,
            },
        }
        
        serializer = StatsSerializer(data)
        return Response(serializer.data)


class EstimateAPIView(APIView):
    """
    API endpoint for estimating cost.
    
    POST /api/estimate/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = EstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_size_mb = serializer.validated_data.get('file_size_mb')
        estimated_duration = serializer.validated_data.get('estimated_duration')
        summary_style = serializer.validated_data.get('summary_style', 'concise')
        api_provider = serializer.validated_data.get('api_provider', 'openai')
        
        # Estimate based on file size and duration
        # Rough estimation: 1 minute of audio ≈ 150 words ≈ 200 tokens
        # Transcription cost: $0.006 per minute (Whisper pricing)
        # Summarization cost: based on tokens
        
        from ..api_client import APIClient
        
        try:
            api_client = APIClient(provider=api_provider)
            
            # Estimate transcription tokens
            if estimated_duration:
                # 1 minute ≈ 200 tokens for transcription
                transcription_tokens = estimated_duration * 200
            else:
                # Fallback: file size based estimation
                transcription_tokens = file_size_mb * 1000  # Rough estimate
            
            # Estimate summary tokens based on style
            summary_token_estimates = {
                'concise': 100,
                'detailed': 300,
                'bullet_points': 200,
                'key_takeaways': 150,
            }
            summary_tokens = summary_token_estimates.get(summary_style, 100)
            
            # Calculate cost
            token_usage = {
                'prompt_tokens': int(transcription_tokens),
                'completion_tokens': summary_tokens,
            }
            
            estimated_cost = api_client.calculate_cost(token_usage)
            
            # Add Whisper transcription cost ($0.006 per minute)
            whisper_cost = 0
            if api_provider == 'openai' and estimated_duration:
                whisper_cost = estimated_duration * 0.006 / 60  # $0.006 per minute
            
            total_cost = estimated_cost + whisper_cost
            
            return Response({
                'estimated_cost': total_cost,
                'breakdown': {
                    'transcription_tokens': int(transcription_tokens),
                    'summary_tokens': summary_tokens,
                    'transcription_cost': estimated_cost,
                    'whisper_cost': whisper_cost,
                },
                'assumptions': {
                    'tokens_per_minute': 200,
                    'summary_style': summary_style,
                    'api_provider': api_provider,
                },
            })
            
        except Exception as e:
            return Response(
                {'error': f'Failed to estimate cost: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class RecordingListAPIView(generics.ListAPIView):
    """
    API endpoint for listing recordings with filtering.
    
    GET /api/recordings/
    """
    serializer_class = AudioRecordingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = AudioRecording.objects.all()
        
        # Apply filters from query parameters
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        api_provider = self.request.query_params.get('api_provider')
        if api_provider:
            queryset = queryset.filter(api_provider=api_provider)
        
        summary_style = self.request.query_params.get('summary_style')
        if summary_style:
            queryset = queryset.filter(summary_style=summary_style)
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(transcribed_text__icontains=search) |
                Q(summary__icontains=search)
            )
        
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset.order_by('-created_at')
