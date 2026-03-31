import os
import time
import logging
from celery import shared_task, current_app
from django.core.files.storage import default_storage
from django.db import transaction
from .models import AudioRecording
from .api_client import APIClient, TranscriptionError, SummarizationError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def transcribe_audio_task(self, recording_id: int):
    """
    Celery task to transcribe audio file.
    
    Args:
        recording_id: ID of the AudioRecording instance
    """
    try:
        # Get recording instance
        recording = AudioRecording.objects.get(id=recording_id)
        
        # Update status
        recording.status = 'transcribing'
        recording.save(update_fields=['status'])
        
        logger.info(f"Starting transcription for recording {recording_id}: {recording.title}")
        
        # Initialize API client
        api_client = APIClient(provider=recording.api_provider)
        
        # Get audio file path
        audio_file_path = recording.audio_file.path
        
        # Check if file exists
        if not os.path.exists(audio_file_path):
            # Try to get from storage
            audio_file_path = default_storage.path(recording.audio_file.name)
        
        # Transcribe audio
        start_time = time.time()
        transcribed_text, metadata = api_client.transcribe_audio(audio_file_path)
        transcription_time = time.time() - start_time
        
        # Save transcription
        recording.transcribed_text = transcribed_text
        recording.status = 'summarizing'
        recording.save(update_fields=['transcribed_text', 'status'])
        
        logger.info(f"Transcription completed for recording {recording_id}. "
                   f"Text length: {len(transcribed_text)} characters. "
                   f"Time: {transcription_time:.2f}s")
        
        # Trigger summarization task (use Celery only for Redis broker; otherwise sync)
        broker_url = str(current_app.conf.broker_url or '')
        if broker_url.startswith('redis://'):
            summarize_text_task.delay(recording_id, recording.summary_style)
        else:
            logger.info("Non-Redis broker detected in transcribe task; running summarize synchronously")
            summarize_text_task.run(recording_id, recording.summary_style)
        
        return {
            'recording_id': recording_id,
            'status': 'transcription_completed',
            'text_length': len(transcribed_text),
            'transcription_time': transcription_time,
        }
        
    except AudioRecording.DoesNotExist:
        logger.error(f"Recording {recording_id} not found")
        raise self.retry(countdown=60, exc=Exception(f"Recording {recording_id} not found"))
    
    except TranscriptionError as e:
        logger.error(f"Transcription failed for recording {recording_id}: {str(e)}")
        
        # Update recording with error
        with transaction.atomic():
            recording = AudioRecording.objects.select_for_update().get(id=recording_id)
            recording.status = 'failed'
            recording.error_message = f"Transcription error: {str(e)}"
            recording.save(update_fields=['status', 'error_message'])
        
        raise self.retry(countdown=60, exc=e)
    
    except Exception as e:
        logger.error(f"Unexpected error in transcription task for recording {recording_id}: {str(e)}")
        
        # Update recording with error
        with transaction.atomic():
            recording = AudioRecording.objects.select_for_update().get(id=recording_id)
            recording.status = 'failed'
            recording.error_message = f"Unexpected error: {str(e)}"
            recording.save(update_fields=['status', 'error_message'])
        
        raise self.retry(countdown=60, exc=e)


@shared_task(bind=True, max_retries=3)
def summarize_text_task(self, recording_id: int, summary_style: str = None):
    """
    Celery task to summarize transcribed text.
    
    Args:
        recording_id: ID of the AudioRecording instance
        summary_style: Style of summary to generate
    """
    try:
        # Get recording instance
        recording = AudioRecording.objects.get(id=recording_id)
        
        # Update status
        recording.status = 'summarizing'
        if summary_style:
            recording.summary_style = summary_style
        recording.save(update_fields=['status', 'summary_style'])
        
        logger.info(f"Starting summarization for recording {recording_id}: {recording.title}")
        
        # Check if we have transcribed text
        if not recording.transcribed_text:
            raise SummarizationError("No transcribed text available for summarization")
        
        # Initialize API client
        api_client = APIClient(provider=recording.api_provider)
        
        # Summarize text
        start_time = time.time()
        summary, token_usage = api_client.summarize_text(
            recording.transcribed_text,
            recording.summary_style
        )
        summarization_time = time.time() - start_time
        
        # Calculate cost
        cost = api_client.calculate_cost(token_usage)
        
        # Calculate total processing time
        total_processing_time = recording.processing_time or 0
        total_processing_time += summarization_time
        
        # Save results
        recording.summary = summary
        recording.token_usage = token_usage
        recording.cost_estimate = cost
        recording.processing_time = total_processing_time
        recording.status = 'completed'
        recording.save(update_fields=[
            'summary', 'token_usage', 'cost_estimate',
            'processing_time', 'status'
        ])
        
        logger.info(f"Summarization completed for recording {recording_id}. "
                   f"Summary length: {len(summary)} characters. "
                   f"Cost: ${cost:.6f}. Time: {summarization_time:.2f}s")
        
        return {
            'recording_id': recording_id,
            'status': 'summarization_completed',
            'summary_length': len(summary),
            'token_usage': token_usage,
            'cost': float(cost),
            'summarization_time': summarization_time,
        }
        
    except AudioRecording.DoesNotExist:
        logger.error(f"Recording {recording_id} not found")
        raise self.retry(countdown=60, exc=Exception(f"Recording {recording_id} not found"))
    
    except SummarizationError as e:
        logger.error(f"Summarization failed for recording {recording_id}: {str(e)}")
        
        # Update recording with error
        with transaction.atomic():
            recording = AudioRecording.objects.select_for_update().get(id=recording_id)
            recording.status = 'failed'
            recording.error_message = f"Summarization error: {str(e)}"
            recording.save(update_fields=['status', 'error_message'])
        
        raise self.retry(countdown=60, exc=e)
    
    except Exception as e:
        logger.error(f"Unexpected error in summarization task for recording {recording_id}: {str(e)}")
        
        # Update recording with error
        with transaction.atomic():
            recording = AudioRecording.objects.select_for_update().get(id=recording_id)
            recording.status = 'failed'
            recording.error_message = f"Unexpected error: {str(e)}"
            recording.save(update_fields=['status', 'error_message'])
        
        raise self.retry(countdown=60, exc=e)


@shared_task
def process_audio_recording(recording_id: int):
    """
    Combined task that handles both transcription and summarization.
    
    Args:
        recording_id: ID of the AudioRecording instance
    """
    try:
        # Start transcription
        transcription_result = transcribe_audio_task.run(recording_id)
        
        # Note: summarization is triggered by transcribe_audio_task
        return transcription_result
        
    except Exception as e:
        logger.error(f"Failed to process recording {recording_id}: {str(e)}")
        raise


@shared_task
def regenerate_summary(recording_id: int, summary_style: str = None, api_provider: str = None):
    """
    Regenerate summary for an existing recording.
    
    Args:
        recording_id: ID of the AudioRecording instance
        summary_style: New summary style (optional)
        api_provider: New API provider (optional)
    """
    try:
        # Get recording instance
        recording = AudioRecording.objects.get(id=recording_id)
        
        # Update provider if specified
        if api_provider and api_provider in ['openai', 'deepseek']:
            recording.api_provider = api_provider
        
        # Save changes
        recording.save(update_fields=['api_provider'] if api_provider else [])
        
        # Trigger summarization with new style (use Celery only for Redis broker; otherwise sync)
        broker_url = str(current_app.conf.broker_url or '')
        if broker_url.startswith('redis://'):
            return summarize_text_task.delay(recording_id, summary_style)

        logger.info("Non-Redis broker detected in regenerate task; running summarize synchronously")
        return summarize_text_task.run(recording_id, summary_style)
        
    except Exception as e:
        logger.error(f"Failed to regenerate summary for recording {recording_id}: {str(e)}")
        raise


@shared_task
def batch_process_recordings(recording_ids: list):
    """
    Process multiple recordings in batch.
    
    Args:
        recording_ids: List of recording IDs to process
    """
    results = []
    for recording_id in recording_ids:
        try:
            result = process_audio_recording.delay(recording_id)
            results.append({
                'recording_id': recording_id,
                'task_id': result.id,
                'status': 'queued'
            })
        except Exception as e:
            results.append({
                'recording_id': recording_id,
                'error': str(e),
                'status': 'failed'
            })
    
    return results
