from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
import os


class AudioRecording(models.Model):
    """Model to store audio recordings and their processing results."""
    
    # Status choices
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('transcribing', 'Transcribing'),
        ('summarizing', 'Summarizing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    # Summary style choices
    SUMMARY_STYLE_CHOICES = [
        ('concise', 'Concise (2-3 sentences)'),
        ('detailed', 'Detailed (comprehensive)'),
        ('bullet_points', 'Bullet Points (5-7 points)'),
        ('key_takeaways', 'Key Takeaways (actionable insights)'),
    ]
    
    # API provider choices
    API_PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('deepseek', 'DeepSeek'),
    ]
    
    # Basic fields
    title = models.CharField(max_length=200)
    
    audio_file = models.FileField(
        upload_to='audio/',
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'MP3'])],
        help_text='Upload MP3 audio file (max 25MB)'
    )
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Processing fields
    transcribed_text = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    summary_style = models.CharField(
        max_length=20,
        choices=SUMMARY_STYLE_CHOICES,
        default='concise'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    task_id = models.CharField(max_length=255, blank=True)
    api_provider = models.CharField(
        max_length=20,
        choices=API_PROVIDER_CHOICES,
        default='openai'
    )
    
    # Token usage and cost tracking
    token_usage = models.JSONField(default=dict, blank=True)
    cost_estimate = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0.00
    )
    
    # Error handling
    error_message = models.TextField(blank=True)
    
    # Performance metrics
    processing_time = models.FloatField(
        help_text='Total processing time in seconds',
        blank=True,
        null=True
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['api_provider']),
        ]
        verbose_name = 'Audio Recording'
        verbose_name_plural = 'Audio Recordings'
    
    def __str__(self):
        return f'{self.title} ({self.status})'
    
    def clean(self):
        """Validate the audio file before saving."""
        super().clean()
        
        if self.audio_file:
            # Check file size (25MB limit)
            max_size = 25 * 1024 * 1024  # 25MB in bytes
            if self.audio_file.size > max_size:
                raise ValidationError(
                    f'File size exceeds 25MB limit. Current size: {self.audio_file.size / (1024*1024):.2f}MB'
                )
            
            # Check file extension
            ext = os.path.splitext(self.audio_file.name)[1].lower()
            if ext not in ['.mp3']:
                raise ValidationError('Only MP3 files are allowed.')
    
    def get_file_size_mb(self):
        """Return file size in MB."""
        if self.audio_file and self.audio_file.size:
            return self.audio_file.size / (1024 * 1024)
        return 0
    
    def get_word_count(self):
        """Return word count of transcribed text."""
        if self.transcribed_text:
            return len(self.transcribed_text.split())
        return 0
    
    def get_summary_word_count(self):
        """Return word count of summary."""
        if self.summary:
            return len(self.summary.split())
        return 0
    
    def get_processing_status_display(self):
        """Return human-readable processing status."""
        status_map = {
            'pending': 'Waiting to process',
            'transcribing': 'Transcribing audio',
            'summarizing': 'Generating summary',
            'completed': 'Completed',
            'failed': 'Failed',
        }
        return status_map.get(self.status, self.status)
    
    def get_cost_display(self):
        """Return formatted cost estimate."""
        return f'${self.cost_estimate:.6f}'
    
    def get_token_usage_summary(self):
        """Return formatted token usage."""
        if not self.token_usage:
            return 'No token data'
        
        tokens = self.token_usage
        return f"Prompt: {tokens.get('prompt_tokens', 0)}, Completion: {tokens.get('completion_tokens', 0)}, Total: {tokens.get('total_tokens', 0)}"