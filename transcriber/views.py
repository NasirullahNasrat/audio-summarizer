from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q, Sum, Avg, Count
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import csv
from datetime import datetime, timedelta

from .models import AudioRecording
from .forms import AudioUploadForm, RegenerateSummaryForm, SearchFilterForm
from .tasks import transcribe_audio_task, summarize_text_task, regenerate_summary


class HomeView(TemplateView):
    """Home page view with upload form and dashboard."""
    template_name = 'transcriber/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add upload form to context
        context['upload_form'] = AudioUploadForm()
        
        # Get recent recordings
        context['recent_recordings'] = AudioRecording.objects.all().order_by('-created_at')[:5]
        
        # Get statistics
        context['total_recordings'] = AudioRecording.objects.count()
        context['completed_recordings'] = AudioRecording.objects.filter(status='completed').count()
        context['total_cost'] = AudioRecording.objects.aggregate(
            total=Sum('cost_estimate')
        )['total'] or 0
        
        # Get processing time stats
        completed = AudioRecording.objects.filter(status='completed', processing_time__isnull=False)
        if completed.exists():
            context['avg_processing_time'] = completed.aggregate(
                avg=Avg('processing_time')
            )['avg']
        else:
            context['avg_processing_time'] = 0
        
        return context


class AudioUploadView(LoginRequiredMixin, CreateView):
    """View for uploading audio files."""
    model = AudioRecording
    form_class = AudioUploadForm
    template_name = 'transcriber/upload.html'
    success_url = reverse_lazy('transcriber:recording_list')
    
    def form_valid(self, form):
        """Process the form and start Celery tasks."""
        # Save the recording
        self.object = form.save()
        
        # Try to start transcription task asynchronously
        try:
            # Check if Celery is available
            from celery import current_app
            if current_app.conf.broker_url and str(current_app.conf.broker_url).startswith('redis://'):
                # Start transcription task asynchronously
                task = transcribe_audio_task.delay(self.object.id)
                self.object.task_id = task.id
                self.object.save(update_fields=['task_id'])
                messages.success(
                    self.request,
                    f'Audio "{self.object.title}" uploaded successfully! '
                    f'Transcription and summarization have started in the background.'
                )
            else:
                # Run synchronously for memory broker / non-Redis broker
                raise Exception("Celery broker is not Redis; using synchronous fallback")
        except Exception as e:
            # Fall back to synchronous execution
            print(f"Celery not available, running synchronously: {e}")
            try:
                # Run transcription synchronously
                transcribe_audio_task.run(self.object.id)
                self.object.refresh_from_db()

                # Hard guard: never keep pending-like status after sync submit
                if self.object.status in ['pending', 'transcribing', 'summarizing']:
                    self.object.status = 'failed'
                    self.object.error_message = 'Processing did not finalize during synchronous execution.'
                    self.object.save(update_fields=['status', 'error_message'])
                messages.success(
                    self.request,
                    f'Audio "{self.object.title}" uploaded successfully! '
                    f'Transcription and summarization completed.'
                )
            except Exception as sync_error:
                # If synchronous execution fails, mark as failed
                self.object.status = 'failed'
                self.object.error_message = str(sync_error)
                self.object.save(update_fields=['status', 'error_message'])
                messages.error(
                    self.request,
                    f'Error processing audio "{self.object.title}": {sync_error}'
                )
        
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add cost estimation data
        from .api_client import APIClient
        api_client = APIClient()
        
        # Sample cost estimates for different file sizes
        context['cost_estimates'] = {
            'small': api_client.estimate_cost_from_text(' ' * 1000, 'concise'),
            'medium': api_client.estimate_cost_from_text(' ' * 5000, 'concise'),
            'large': api_client.estimate_cost_from_text(' ' * 15000, 'concise'),
        }
        
        return context


class RecordingListView(LoginRequiredMixin, ListView):
    """View for listing all recordings with filtering."""
    model = AudioRecording
    template_name = 'transcriber/list.html'
    context_object_name = 'recordings'
    paginate_by = 10
    
    def get_queryset(self):
        """Filter recordings based on search parameters."""
        queryset = super().get_queryset()
        
        # Get filter parameters
        search = self.request.GET.get('search', '')
        status = self.request.GET.get('status', '')
        summary_style = self.request.GET.get('summary_style', '')
        api_provider = self.request.GET.get('api_provider', '')
        date_from = self.request.GET.get('date_from', '')
        date_to = self.request.GET.get('date_to', '')
        
        # Apply filters
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(transcribed_text__icontains=search) |
                Q(summary__icontains=search)
            )
        
        if status:
            queryset = queryset.filter(status=status)
        
        if summary_style:
            queryset = queryset.filter(summary_style=summary_style)
        
        if api_provider:
            queryset = queryset.filter(api_provider=api_provider)
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter form with current values
        context['filter_form'] = SearchFilterForm(self.request.GET or None)
        
        # Add statistics
        context['total_count'] = self.get_queryset().count()
        context['total_cost'] = self.get_queryset().aggregate(
            total=Sum('cost_estimate')
        )['total'] or 0
        
        # Status distribution
        status_counts = {}
        for status_code, status_name in AudioRecording.STATUS_CHOICES:
            count = self.get_queryset().filter(status=status_code).count()
            if count > 0:
                status_counts[status_name] = count
        context['status_counts'] = status_counts
        
        # Provider distribution
        provider_counts = {}
        for provider_code, provider_name in AudioRecording.API_PROVIDER_CHOICES:
            count = self.get_queryset().filter(api_provider=provider_code).count()
            if count > 0:
                provider_counts[provider_name] = count
        context['provider_counts'] = provider_counts
        
        return context


class RecordingDetailView(LoginRequiredMixin, DetailView):
    """View for displaying recording details."""
    model = AudioRecording
    template_name = 'transcriber/detail.html'
    context_object_name = 'recording'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add regenerate form
        context['regenerate_form'] = RegenerateSummaryForm(initial={
            'summary_style': self.object.summary_style,
            'api_provider': self.object.api_provider,
        })
        
        # Add word counts
        context['transcription_word_count'] = self.object.get_word_count()
        context['summary_word_count'] = self.object.get_summary_word_count()
        
        return context


class RegenerateSummaryView(LoginRequiredMixin, UpdateView):
    """View for regenerating summary with different options."""
    model = AudioRecording
    form_class = RegenerateSummaryForm
    template_name = 'transcriber/regenerate.html'
    
    def form_valid(self, form):
        """Process the form and trigger regeneration task."""
        summary_style = form.cleaned_data['summary_style']
        api_provider = form.cleaned_data['api_provider']
        
        # Update recording with new provider if changed
        if api_provider != self.object.api_provider:
            self.object.api_provider = api_provider
            self.object.save(update_fields=['api_provider'])
        
        # Trigger regeneration task (with sync fallback when Redis/Celery unavailable)
        try:
            from celery import current_app
            if not (current_app.conf.broker_url and str(current_app.conf.broker_url).startswith('redis://')):
                raise Exception("Celery broker is not Redis; using synchronous fallback")

            task = regenerate_summary.delay(self.object.id, summary_style, api_provider)
            self.object.task_id = task.id
            self.object.status = 'summarizing'
            self.object.save(update_fields=['task_id', 'status'])

            messages.success(
                self.request,
                f'Summary regeneration started for "{self.object.title}"! '
                f'New style: {summary_style}, Provider: {api_provider}.'
            )
        except Exception as e:
            print(f"Celery not available for regeneration, running synchronously: {e}")
            try:
                regenerate_summary.run(self.object.id, summary_style, api_provider)
                self.object.refresh_from_db()

                # Hard guard: never keep pending-like status after sync submit
                if self.object.status in ['pending', 'transcribing', 'summarizing']:
                    self.object.status = 'failed'
                    self.object.error_message = 'Regeneration did not finalize during synchronous execution.'
                    self.object.save(update_fields=['status', 'error_message'])
                self.object.status = 'completed'
                self.object.save(update_fields=['status'])
                messages.success(
                    self.request,
                    f'Summary regenerated synchronously for "{self.object.title}". '
                    f'New style: {summary_style}, Provider: {api_provider}.'
                )
            except Exception as sync_error:
                self.object.status = 'failed'
                self.object.error_message = str(sync_error)
                self.object.save(update_fields=['status', 'error_message'])
                messages.error(
                    self.request,
                    f'Error regenerating summary for "{self.object.title}": {sync_error}'
                )
        
        return redirect('transcriber:recording_detail', pk=self.object.pk)
    
    def get_success_url(self):
        return reverse_lazy('transcriber:recording_detail', kwargs={'pk': self.object.pk})


@method_decorator(csrf_exempt, name='dispatch')
class RecordingStatusView(LoginRequiredMixin, DetailView):
    """API view for getting recording status (JSON response)."""
    model = AudioRecording
    
    def get(self, request, *args, **kwargs):
        recording = self.get_object()
        
        # Get task status if available
        task_status = 'unknown'
        if recording.task_id:
            from celery.result import AsyncResult
            task_result = AsyncResult(recording.task_id)
            task_status = task_result.status
        
        response_data = {
            'id': recording.id,
            'title': recording.title,
            'status': recording.status,
            'task_status': task_status,
            'progress': self._get_progress_percentage(recording.status),
            'transcribed_text_length': len(recording.transcribed_text),
            'summary_length': len(recording.summary),
            'cost_estimate': float(recording.cost_estimate),
            'processing_time': recording.processing_time,
            'updated_at': recording.updated_at.isoformat(),
        }
        
        return JsonResponse(response_data)
    
    def _get_progress_percentage(self, status):
        """Map status to progress percentage."""
        progress_map = {
            'pending': 10,
            'transcribing': 40,
            'summarizing': 70,
            'completed': 100,
            'failed': 0,
        }
        return progress_map.get(status, 0)


def download_transcription(request, pk):
    """Download transcription as text file."""
    recording = get_object_or_404(AudioRecording, pk=pk)
    
    if not recording.transcribed_text:
        messages.error(request, 'No transcription available for download.')
        return redirect('recording_detail', pk=pk)
    
    response = HttpResponse(recording.transcribed_text, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="{recording.title}_transcription.txt"'
    return response


def download_summary(request, pk):
    """Download summary as text file."""
    recording = get_object_or_404(AudioRecording, pk=pk)
    
    if not recording.summary:
        messages.error(request, 'No summary available for download.')
        return redirect('recording_detail', pk=pk)
    
    response = HttpResponse(recording.summary, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="{recording.title}_summary.txt"'
    return response


def export_recordings_csv(request):
    """Export recordings as CSV file."""
    recordings = AudioRecording.objects.all().order_by('-created_at')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audio_recordings.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'ID', 'Title', 'Status', 'API Provider', 'Summary Style',
        'File Size (MB)', 'Transcription Length', 'Summary Length',
        'Cost Estimate', 'Processing Time (s)', 'Created At', 'Updated At'
    ])
    
    # Write data
    for recording in recordings:
        writer.writerow([
            recording.id,
            recording.title,
            recording.get_status_display(),
            recording.get_api_provider_display(),
            recording.get_summary_style_display(),
            f"{recording.get_file_size_mb():.2f}",
            len(recording.transcribed_text),
            len(recording.summary),
            f"{recording.cost_estimate:.6f}",
            f"{recording.processing_time or 0:.2f}",
            recording.created_at.isoformat(),
            recording.updated_at.isoformat(),
        ])
    
    return response


def get_statistics(request):
    """Get statistics data for charts (JSON API)."""
    # Get date range (last 30 days by default)
    days = int(request.GET.get('days', 30))
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Get daily statistics
    daily_stats = []
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        day_recordings = AudioRecording.objects.filter(
            created_at__date=current_date.date()
        )
        
        daily_stats.append({
            'date': date_str,
            'count': day_recordings.count(),
            'cost': float(day_recordings.aggregate(
                total=Sum('cost_estimate')
            )['total'] or 0),
            'completed': day_recordings.filter(status='completed').count(),
        })
        
        current_date += timedelta(days=1)
    
    # Get provider statistics
    provider_stats = []
    for provider_code, provider_name in AudioRecording.API_PROVIDER_CHOICES:
        provider_recordings = AudioRecording.objects.filter(api_provider=provider_code)
        provider_stats.append({
            'provider': provider_name,
            'count': provider_recordings.count(),
            'cost': float(provider_recordings.aggregate(
                total=Sum('cost_estimate')
            )['total'] or 0),
        })
    
    # Get style statistics
    style_stats = []
    for style_code, style_name in AudioRecording.SUMMARY_STYLE_CHOICES:
        style_recordings = AudioRecording.objects.filter(summary_style=style_code)
        style_stats.append({
            'style': style_name,
            'count': style_recordings.count(),
        })
    
    return JsonResponse({
        'daily_stats': daily_stats,
        'provider_stats': provider_stats,
        'style_stats': style_stats,
        'total_recordings': AudioRecording.objects.count(),
        'total_cost': float(AudioRecording.objects.aggregate(
            total=Sum('cost_estimate')
        )['total'] or 0),
        'avg_processing_time': float(AudioRecording.objects.filter(
            processing_time__isnull=False
        ).aggregate(
            avg=Avg('processing_time')
        )['avg'] or 0),
    })
