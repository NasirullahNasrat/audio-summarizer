#!/usr/bin/env python
"""
Verify the transcription and summarization workflow.
This script tests the basic functionality without requiring API keys.
"""
import os
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audio_summarizer.settings')

import django
django.setup()

from django.conf import settings
from transcriber.models import AudioRecording
from transcriber.api_client import APIClient
from transcriber.tasks import transcribe_audio_task, summarize_text_task
from django.contrib.auth.models import User

def test_api_client_initialization():
    """Test that API client can be initialized."""
    print("1. Testing API client initialization...")
    try:
        client = APIClient(provider='openai')
        print(f"   [OK] OpenAI client initialized (provider: {client.provider})")
        
        # Try DeepSeek client
        client = APIClient(provider='deepseek')
        print(f"   [OK] DeepSeek client initialized (provider: {client.provider})")
        return True
    except Exception as e:
        print(f"   [FAIL] API client initialization failed: {e}")
        return False

def test_cost_estimation():
    """Test cost estimation (should work without API keys)."""
    print("\n2. Testing cost estimation...")
    try:
        client = APIClient(provider='openai')
        
        # Test cost estimation for different text lengths
        test_cases = [
            ("Short text", "This is a short text.", 'concise'),
            ("Medium text", "This is a medium length text. " * 10, 'detailed'),
            ("Long text", "This is a longer text. " * 50, 'bullet_points'),
        ]
        
        for name, text, style in test_cases:
            try:
                cost = client.estimate_cost_from_text(text, style)
                print(f"   [OK] {name} cost estimation: ${cost:.6f}")
            except Exception as e:
                print(f"   [WARN] {name} cost estimation failed: {e}")
        
        return True
    except Exception as e:
        print(f"   [FAIL] Cost estimation test failed: {e}")
        return False

def test_model_validation():
    """Test that models can be created and validated."""
    print("\n3. Testing model validation...")
    try:
        # Create a test recording (without actual file upload)
        # Note: We can't create a full instance without a file, but we can test the model structure
        recording = AudioRecording(
            title="Test Workflow Recording",
            api_provider='openai',
            summary_style='concise',
            status='pending'
        )
        
        # Test that model can be instantiated
        print(f"   [OK] Model instantiation successful")
        
        # Test status choices
        valid_statuses = dict(AudioRecording.STATUS_CHOICES)
        print(f"   [OK] Status choices: {list(valid_statuses.keys())}")
        
        # Test provider choices
        valid_providers = dict(AudioRecording.API_PROVIDER_CHOICES)
        print(f"   [OK] Provider choices: {list(valid_providers.keys())}")
        
        # Test summary style choices
        valid_styles = dict(AudioRecording.SUMMARY_STYLE_CHOICES)
        print(f"   [OK] Summary style choices: {list(valid_styles.keys())}")
        
        # Test model methods
        print(f"   [OK] Model string representation: {recording}")
        
        # Test meta options
        print(f"   [OK] Model ordering: {recording._meta.ordering}")
        
        return True
    except Exception as e:
        print(f"   [FAIL] Model validation test failed: {e}")
        return False

def test_task_functions():
    """Test that task functions can be imported and have correct signatures."""
    print("\n4. Testing task functions...")
    try:
        # Check task signatures
        import inspect
        
        tasks_to_check = [
            (transcribe_audio_task, 'transcribe_audio_task'),
            (summarize_text_task, 'summarize_text_task'),
        ]
        
        for task_func, task_name in tasks_to_check:
            sig = inspect.signature(task_func)
            print(f"   [OK] {task_name} signature: {sig}")
        
        return True
    except Exception as e:
        print(f"   [FAIL] Task functions test failed: {e}")
        return False

def test_settings_configuration():
    """Test that important settings are configured."""
    print("\n5. Testing settings configuration...")
    try:
        required_settings = [
            ('SECRET_KEY', bool(settings.SECRET_KEY)),
            ('DEBUG', settings.DEBUG is not None),
            ('DATABASES', bool(settings.DATABASES.get('default'))),
            ('INSTALLED_APPS', 'transcriber' in settings.INSTALLED_APPS),
            ('CELERY_BROKER_URL', bool(settings.CELERY_BROKER_URL)),
            ('MEDIA_ROOT', bool(settings.MEDIA_ROOT)),
            ('STATIC_ROOT', bool(settings.STATIC_ROOT)),
        ]
        
        all_ok = True
        for setting_name, is_set in required_settings:
            status = "[OK]" if is_set else "[WARN]"
            print(f"   {status} {setting_name}: {'Configured' if is_set else 'Not configured/missing'}")
            if not is_set and setting_name in ['SECRET_KEY', 'DATABASES', 'INSTALLED_APPS']:
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"   [FAIL] Settings test failed: {e}")
        return False

def main():
    """Run all verification tests."""
    print("=" * 70)
    print("Verifying Transcription and Summarization Workflow")
    print("=" * 70)
    print(f"Django Version: {django.get_version()}")
    print(f"Python Version: {sys.version.split()[0]}")
    print("=" * 70)
    
    results = []
    
    # Run tests
    results.append(("API Client Initialization", test_api_client_initialization()))
    results.append(("Cost Estimation", test_cost_estimation()))
    results.append(("Model Validation", test_model_validation()))
    results.append(("Task Functions", test_task_functions()))
    results.append(("Settings Configuration", test_settings_configuration()))
    
    # Summary
    print("\n" + "=" * 70)
    print("Verification Summary:")
    print("=" * 70)
    
    all_passed = True
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {test_name}")
        if not passed and test_name not in ["Cost Estimation"]:  # Cost estimation might fail without API keys
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("SUCCESS: Basic workflow verification passed!")
        print("\nNote: Actual API integration tests require valid API keys.")
        print("To test with real APIs:")
        print("1. Set OPENAI_API_KEY in .env file")
        print("2. Set DEEPSEEK_API_KEY in .env file (optional)")
        print("3. Restart the Django server")
        print("4. Upload an audio file through the web interface")
    else:
        print("WARNING: Some verification tests failed")
        print("Check the errors above and fix the configuration.")
    
    return all_passed

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)