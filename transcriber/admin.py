from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from datetime import timedelta
import json

from .models import AudioRecording
from .tasks import transcribe_audio_task, regenerate_summary


@admin.register(AudioRecording)
class AudioRecordingAdmin(admin.ModelAdmin):
    """Admin interface for AudioRecording model."""
    
    list_display = [
        'title', 'status_badge', 'api_provider_display',
        'summary_style_display', 'cost_estimate_display',
        'processing_time_display', 'created_at', 'action_buttons'
    ]
    
    list_filter = [
        'status', 'api_provider', 'summary_style',
        'created_at', 'updated_at'
    ]
    
    search_fields = [
        'title', 'transcribed_text', 'summary', 'error_message'
    ]
    
    readonly_fields = [
        'uploaded_at', 'created_at', 'updated_at',
        'processing_time', 'cost_estimate', 'token_usage_display',
        'file_size_display', 'word_count_display', 'summary_word_count_display'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'audio_file', 'uploaded_at')
        }),
        ('Processing Settings', {
            'fields': ('summary_style', 'api_provider', 'status', 'task_id')
        }),
        ('Results', {
            'fields': ('transcribed_text', 'summary', 'error_message')
        }),
        ('Metrics', {
            'fields': (
                'processing_time', 'cost_estimate',
                'token_usage_display', 'file_size_display',
                'word_count_display', 'summary_word_count_display'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['retry_failed_tasks', 'export_as_csv', 'calculate_statistics']
    
    def status_badge(self, obj):
        """Display status as a colored badge."""
        status_colors = {
            'pending': 'secondary',
            'transcribing': 'info',
            'summarizing': 'warning',
            'completed': 'success',
            'failed': 'danger',
        }
        
        color = status_colors.get(obj.status, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    def api_provider_display(self, obj):
        """Display API provider with icon."""
        providers = {
            'openai': '🤖',
            'deepseek': '🧠',
        }
        icon = providers.get(obj.api_provider, '🔧')
        return f'{icon} {obj.get_api_provider_display()}'
    api_provider_display.short_description = 'API Provider'
    
    def summary_style_display(self, obj):
        """Display summary style with icon."""
        styles = {
            'concise': '📝',
            'detailed': '📋',
            'bullet_points': '📌',
            'key_takeaways': '💡',
        }
        icon = styles.get(obj.summary_style, '📄')
        return f'{icon} {obj.get_summary_style_display()}'
    summary_style_display.short_description = 'Summary Style'
    
    def cost_estimate_display(self, obj):
        """Display cost estimate formatted."""
        if obj.cost_estimate:
            return f'${obj.cost_estimate:.6f}'
        return '-'
    cost_estimate_display.short_description = 'Cost'
    cost_estimate_display.admin_order_field = 'cost_estimate'
    
    def processing_time_display(self, obj):
        """Display processing time formatted."""
        if obj.processing_time:
            return f'{obj.processing_time:.2f}s'
        return '-'
    processing_time_display.short_description = 'Time'
    processing_time_display.admin_order_field = 'processing_time'
    
    def action_buttons(self, obj):
        """Display action buttons."""
        buttons = []
        
        # View button
        view_url = reverse('admin:transcriber_audiorecording_change', args=[obj.id])
        buttons.append(
            f'<a href="{view_url}" class="button" title="View/Edit">👁️</a>'
        )
        
        # Retry button for failed tasks
        if obj.status == 'failed':
            retry_url = reverse('admin:transcriber_audiorecording_retry', args=[obj.id])
            buttons.append(
                f'<a href="{retry_url}" class="button" title="Retry">🔄</a>'
            )
        
        # Regenerate button for completed tasks
        if obj.status == 'completed':
            regenerate_url = reverse('admin:transcriber_audiorecording_regenerate', args=[obj.id])
            buttons.append(
                f'<a href="{regenerate_url}" class="button" title="Regenerate">🔄</a>'
            )
        
        return format_html(' '.join(buttons))
    action_buttons.short_description = 'Actions'
    
    def token_usage_display(self, obj):
        """Display token usage as formatted JSON."""
        if obj.token_usage:
            return format_html(
                '<pre style="background: #f5f5f5; padding: 5px; border-radius: 3px;">{}</pre>',
                json.dumps(obj.token_usage, indent=2)
            )
        return '-'
    token_usage_display.short_description = 'Token Usage'
    
    def file_size_display(self, obj):
        """Display file size in MB."""
        return f'{obj.get_file_size_mb():.2f} MB'
    file_size_display.short_description = 'File Size'
    
    def word_count_display(self, obj):
        """Display word count."""
        return f'{obj.get_word_count()} words'
    word_count_display.short_description = 'Transcription Words'
    
    def summary_word_count_display(self, obj):
        """Display summary word count."""
        return f'{obj.get_summary_word_count()} words'
    summary_word_count_display.short_description = 'Summary Words'
    
    def retry_failed_tasks(self, request, queryset):
        """Admin action to retry failed tasks."""
        failed_recordings = queryset.filter(status='failed')
        count = 0
        
        for recording in failed_recordings:
            try:
                # Reset status and retry
                recording.status = 'pending'
                recording.error_message = ''
                recording.save(update_fields=['status', 'error_message'])
                
                # Start transcription task
                task = transcribe_audio_task.delay(recording.id)
                recording.task_id = task.id
                recording.save(update_fields=['task_id'])
                
                count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Failed to retry recording {recording.id}: {str(e)}',
                    level='error'
                )
        
        self.message_user(
            request,
            f'Successfully retried {count} failed recording(s).',
            level='success'
        )
    retry_failed_tasks.short_description = 'Retry failed tasks'
    
    def export_as_csv(self, request, queryset):
        """Admin action to export selected recordings as CSV."""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audio_recordings_export.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'ID', 'Title', 'Status', 'API Provider', 'Summary Style',
            'File Size (MB)', 'Transcription Length', 'Summary Length',
            'Cost Estimate', 'Processing Time (s)', 'Created At', 'Updated At'
        ])
        
        # Write data
        for recording in queryset:
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
    export_as_csv.short_description = 'Export selected as CSV'
    
    def calculate_statistics(self, request, queryset):
        """Admin action to calculate statistics for selected recordings."""
        total_count = queryset.count()
        completed_count = queryset.filter(status='completed').count()
        failed_count = queryset.filter(status='failed').count()
        
        total_cost = queryset.aggregate(total=Sum('cost_estimate'))['total'] or 0
        avg_processing_time = queryset.filter(
            processing_time__isnull=False
        ).aggregate(avg=Avg('processing_time'))['avg'] or 0
        
        # Provider distribution
        provider_stats = {}
        for provider_code, provider_name in AudioRecording.API_PROVIDER_CHOICES:
            count = queryset.filter(api_provider=provider_code).count()
            if count > 0:
                provider_stats[provider_name] = count
        
        # Style distribution
        style_stats = {}
        for style_code, style_name in AudioRecording.SUMMARY_STYLE_CHOICES:
            count = queryset.filter(summary_style=style_code).count()
            if count > 0:
                style_stats[style_name] = count
        
        # Create statistics message
        message = f"""
        Statistics for {total_count} selected recording(s):
        
        • Status: {completed_count} completed, {failed_count} failed
        • Total Cost: ${total_cost:.6f}
        • Average Processing Time: {avg_processing_time:.2f}s
        
        Provider Distribution:
        {chr(10).join(f'  • {provider}: {count}' for provider, count in provider_stats.items())}
        
        Style Distribution:
        {chr(10).join(f'  • {style}: {count}' for style, count in style_stats.items())}
        """
        
        self.message_user(request, message, level='info')
    calculate_statistics.short_description = 'Calculate statistics'
    
    def get_urls(self):
        """Add custom URLs for admin actions."""
        from django.urls import path
        
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:recording_id>/retry/',
                self.admin_site.admin_view(self.retry_view),
                name='transcriber_audiorecording_retry'
            ),
            path(
                '<int:recording_id>/regenerate/',
                self.admin_site.admin_view(self.regenerate_view),
                name='transcriber_audiorecording_regenerate'
            ),
        ]
        return custom_urls + urls
    
    def retry_view(self, request, recording_id):
        """View for retrying a failed recording."""
        from django.shortcuts import redirect
        
        recording = AudioRecording.objects.get(id=recording_id)
        
        if recording.status == 'failed':
            # Reset and retry
            recording.status = 'pending'
            recording.error_message = ''
            recording.save(update_fields=['status', 'error_message'])
            
            # Start transcription task
            task = transcribe_audio_task.delay(recording.id)
            recording.task_id = task.id
            recording.save(update_fields=['task_id'])
            
            self.message_user(
                request,
                f'Recording "{recording.title}" has been queued for retry.',
                level='success'
            )
        
        return redirect('admin:transcriber_audiorecording_changelist')
    
    def regenerate_view(self, request, recording_id):
        """View for regenerating a completed recording."""
        from django.shortcuts import redirect
        
        recording = AudioRecording.objects.get(id=recording_id)
        
        if recording.status == 'completed' and recording.transcribed_text:
            # Trigger regeneration with current settings
            task = regenerate_summary.delay(
                recording.id,
                recording.summary_style,
                recording.api_provider
            )
            recording.task_id = task.id
            recording.status = 'summarizing'
            recording.save(update_fields=['task_id', 'status'])
            
            self.message_user(
                request,
                f'Summary regeneration started for "{recording.title}".',
                level='success'
            )
        
        return redirect('admin:transcriber_audiorecording_changelist')
    
    class Media:
        """Add custom CSS for admin interface."""
        css = {
            'all': ('admin/css/custom.css',)
        }
        
        js = ('admin/js/custom.js',)