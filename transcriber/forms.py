from django import forms
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from .models import AudioRecording
import os


class AudioUploadForm(forms.ModelForm):
    """Form for uploading audio files."""
    
    class Meta:
        model = AudioRecording
        fields = ['title', 'audio_file', 'summary_style', 'api_provider']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter a descriptive title for your audio',
                'required': True,
            }),
            'audio_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.mp3,audio/mp3',
                'required': True,
            }),
            'summary_style': forms.Select(attrs={
                'class': 'form-select',
            }),
            'api_provider': forms.Select(attrs={
                'class': 'form-select',
            }),
        }
        help_texts = {
            'audio_file': 'Upload MP3 audio file (max 25MB)',
            'summary_style': 'Choose how you want the summary to be formatted',
            'api_provider': 'Choose which AI provider to use for processing',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial values
        self.fields['summary_style'].initial = 'concise'
        self.fields['api_provider'].initial = 'openai'
        
        # Add Bootstrap classes to all fields
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'
    
    def clean_audio_file(self):
        """Validate the audio file."""
        audio_file = self.cleaned_data.get('audio_file')
        
        if not audio_file:
            raise ValidationError('Please select an audio file to upload.')
        
        # Check file extension
        ext = os.path.splitext(audio_file.name)[1].lower()
        if ext not in ['.mp3']:
            raise ValidationError('Only MP3 files are allowed. Please upload a .mp3 file.')
        
        # Check file size (25MB limit)
        max_size = 25 * 1024 * 1024  # 25MB in bytes
        if audio_file.size > max_size:
            raise ValidationError(
                f'File size exceeds 25MB limit. '
                f'Current size: {audio_file.size / (1024*1024):.2f}MB. '
                f'Please upload a smaller file.'
            )
        
        # Check MIME type (basic validation)
        if hasattr(audio_file, 'content_type'):
            content_type = audio_file.content_type
            if content_type not in ['audio/mpeg', 'audio/mp3', 'audio/mp4']:
                raise ValidationError(f'Invalid file type: {content_type}. Please upload an MP3 audio file.')
        
        return audio_file
    
    def clean(self):
        """Additional form-wide validation."""
        cleaned_data = super().clean()
        
        # Check if API keys are configured based on provider selection
        api_provider = cleaned_data.get('api_provider')
        
        if api_provider == 'openai':
            from django.conf import settings
            if not settings.OPENAI_API_KEY:
                self.add_error(
                    'api_provider',
                    'OpenAI API key is not configured. Please contact the administrator.'
                )
        elif api_provider == 'deepseek':
            from django.conf import settings
            if not settings.DEEPSEEK_API_KEY:
                self.add_error(
                    'api_provider',
                    'DeepSeek API key is not configured. Please contact the administrator.'
                )
        
        return cleaned_data


class RegenerateSummaryForm(forms.Form):
    """Form for regenerating summary with different options."""
    
    summary_style = forms.ChoiceField(
        choices=AudioRecording.SUMMARY_STYLE_CHOICES,
        initial='concise',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Choose a different summary style'
    )
    
    api_provider = forms.ChoiceField(
        choices=AudioRecording.API_PROVIDER_CHOICES,
        initial='openai',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Choose a different AI provider'
    )
    
    def __init__(self, *args, **kwargs):
        # Remove 'instance' from kwargs if present (UpdateView passes it)
        kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'


class SearchFilterForm(forms.Form):
    """Form for filtering and searching recordings."""
    
    STATUS_CHOICES = [('', 'All Statuses')] + AudioRecording.STATUS_CHOICES
    SUMMARY_STYLE_CHOICES = [('', 'All Styles')] + AudioRecording.SUMMARY_STYLE_CHOICES
    API_PROVIDER_CHOICES = [('', 'All Providers')] + AudioRecording.API_PROVIDER_CHOICES
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by title or content...',
        }),
        help_text='Search in titles, transcriptions, or summaries'
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    
    summary_style = forms.ChoiceField(
        choices=SUMMARY_STYLE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    
    api_provider = forms.ChoiceField(
        choices=API_PROVIDER_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        help_text='Filter from date'
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        help_text='Filter to date'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial values
        self.fields['search'].initial = ''
        self.fields['status'].initial = ''
        self.fields['summary_style'].initial = ''
        self.fields['api_provider'].initial = ''
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'