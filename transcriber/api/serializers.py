from rest_framework import serializers
from django.core.validators import FileExtensionValidator
from ..models import AudioRecording


class AudioRecordingSerializer(serializers.ModelSerializer):
    """Serializer for AudioRecording model."""
    
    file_size_mb = serializers.SerializerMethodField()
    word_count = serializers.SerializerMethodField()
    summary_word_count = serializers.SerializerMethodField()
    processing_status_display = serializers.SerializerMethodField()
    cost_display = serializers.SerializerMethodField()
    token_usage_summary = serializers.SerializerMethodField()
    
    class Meta:
        model = AudioRecording
        fields = [
            'id', 'title', 'audio_file', 'uploaded_at',
            'transcribed_text', 'summary', 'summary_style',
            'status', 'task_id', 'api_provider', 'token_usage',
            'cost_estimate', 'error_message', 'processing_time',
            'created_at', 'updated_at',
            'file_size_mb', 'word_count', 'summary_word_count',
            'processing_status_display', 'cost_display', 'token_usage_summary',
        ]
        read_only_fields = [
            'id', 'uploaded_at', 'transcribed_text', 'summary',
            'status', 'task_id', 'token_usage', 'cost_estimate',
            'error_message', 'processing_time', 'created_at', 'updated_at',
        ]
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
    
    def get_word_count(self, obj):
        return obj.get_word_count()
    
    def get_summary_word_count(self, obj):
        return obj.get_summary_word_count()
    
    def get_processing_status_display(self, obj):
        return obj.get_processing_status_display()
    
    def get_cost_display(self, obj):
        return obj.get_cost_display()
    
    def get_token_usage_summary(self, obj):
        return obj.get_token_usage_summary()


class AudioUploadSerializer(serializers.ModelSerializer):
    """Serializer for audio file upload."""
    
    audio_file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'MP3'])],
        help_text='Upload MP3 audio file (max 25MB)'
    )
    
    class Meta:
        model = AudioRecording
        fields = ['title', 'audio_file', 'summary_style', 'api_provider']
    
    def validate_audio_file(self, value):
        """Validate the audio file."""
        # Check file size (25MB limit)
        max_size = 25 * 1024 * 1024  # 25MB in bytes
        if value.size > max_size:
            raise serializers.ValidationError(
                f'File size exceeds 25MB limit. '
                f'Current size: {value.size / (1024*1024):.2f}MB'
            )
        
        # Check file extension
        import os
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in ['.mp3']:
            raise serializers.ValidationError('Only MP3 files are allowed.')
        
        return value
    
    def validate(self, data):
        """Additional validation."""
        # Check if API keys are configured based on provider selection
        api_provider = data.get('api_provider', 'openai')
        
        from django.conf import settings
        
        if api_provider == 'openai' and not settings.OPENAI_API_KEY:
            raise serializers.ValidationError({
                'api_provider': 'OpenAI API key is not configured.'
            })
        elif api_provider == 'deepseek' and not settings.DEEPSEEK_API_KEY:
            raise serializers.ValidationError({
                'api_provider': 'DeepSeek API key is not configured.'
            })
        
        return data


class StatusSerializer(serializers.ModelSerializer):
    """Serializer for recording status."""
    
    progress = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = AudioRecording
        fields = [
            'id', 'title', 'status', 'progress',
            'transcribed_text', 'summary', 'cost_estimate',
            'processing_time', 'updated_at', 'file_size_mb',
        ]
    
    def get_progress(self, obj):
        """Map status to progress percentage."""
        progress_map = {
            'pending': 10,
            'transcribing': 40,
            'summarizing': 70,
            'completed': 100,
            'failed': 0,
        }
        return progress_map.get(obj.status, 0)
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()


class RegenerateSerializer(serializers.Serializer):
    """Serializer for regenerating summary."""
    
    summary_style = serializers.ChoiceField(
        choices=AudioRecording.SUMMARY_STYLE_CHOICES,
        default='concise',
        required=False
    )
    
    api_provider = serializers.ChoiceField(
        choices=AudioRecording.API_PROVIDER_CHOICES,
        default='openai',
        required=False
    )
    
    def validate(self, data):
        """Validate that at least one field is provided."""
        if not data.get('summary_style') and not data.get('api_provider'):
            raise serializers.ValidationError(
                'At least one of summary_style or api_provider must be provided.'
            )
        return data


class StatsSerializer(serializers.Serializer):
    """Serializer for statistics data."""
    
    total_recordings = serializers.IntegerField()
    completed_recordings = serializers.IntegerField()
    total_cost = serializers.FloatField()
    avg_processing_time = serializers.FloatField()
    total_tokens = serializers.IntegerField()
    
    provider_stats = serializers.ListField(
        child=serializers.DictField()
    )
    
    style_stats = serializers.ListField(
        child=serializers.DictField()
    )
    
    daily_stats = serializers.ListField(
        child=serializers.DictField()
    )
    
    date_range = serializers.DictField()


class EstimateSerializer(serializers.Serializer):
    """Serializer for cost estimation."""
    
    file_size_mb = serializers.FloatField(
        required=True,
        min_value=0.1,
        max_value=25.0,
        help_text='File size in megabytes (0.1-25 MB)'
    )
    
    estimated_duration = serializers.FloatField(
        required=False,
        min_value=1,
        max_value=60 * 60,  # 1 hour max
        help_text='Estimated audio duration in seconds'
    )
    
    summary_style = serializers.ChoiceField(
        choices=AudioRecording.SUMMARY_STYLE_CHOICES,
        default='concise',
        required=False
    )
    
    api_provider = serializers.ChoiceField(
        choices=AudioRecording.API_PROVIDER_CHOICES,
        default='openai',
        required=False
    )
    
    def validate(self, data):
        """Validate estimation parameters."""
        file_size_mb = data.get('file_size_mb', 0)
        
        if file_size_mb > 25:
            raise serializers.ValidationError({
                'file_size_mb': 'File size cannot exceed 25MB.'
            })
        
        return data


class RecordingFilterSerializer(serializers.Serializer):
    """Serializer for recording filter parameters."""
    
    status = serializers.ChoiceField(
        choices=[('', 'All')] + AudioRecording.STATUS_CHOICES,
        required=False,
        allow_blank=True
    )
    
    api_provider = serializers.ChoiceField(
        choices=[('', 'All')] + AudioRecording.API_PROVIDER_CHOICES,
        required=False,
        allow_blank=True
    )
    
    summary_style = serializers.ChoiceField(
        choices=[('', 'All')] + AudioRecording.SUMMARY_STYLE_CHOICES,
        required=False,
        allow_blank=True
    )
    
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200
    )
    
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    
    page = serializers.IntegerField(
        required=False,
        min_value=1,
        default=1
    )
    
    page_size = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        default=10
    )