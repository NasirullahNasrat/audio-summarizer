from django.apps import AppConfig


class TranscriberConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'transcriber'
    verbose_name = 'Audio Transcriber'
    
    def ready(self):
        """Import signals when app is ready."""
        try:
            import transcriber.signals  # noqa: F401
        except ImportError:
            pass