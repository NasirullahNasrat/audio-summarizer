#!/usr/bin/env python
"""
Verification script for audio summarizer installation.
Checks that all components are working correctly.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audio_summarizer.settings')

try:
    django.setup()
except Exception as e:
    print(f"✗ Django setup failed: {e}")
    sys.exit(1)

def check_database():
    """Check database connectivity and models."""
    print("Checking database...")
    try:
        from django.db import connection
        from transcriber.models import AudioRecording
        
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        
        if result and result[0] == 1:
            print("[OK] Database connection successful")
        else:
            print("[FAIL] Database connection test failed")
            return False
        
        # Test model
        count = AudioRecording.objects.count()
        print(f"[OK] AudioRecording model accessible ({count} records)")
        
        return True
    except Exception as e:
        print(f"[FAIL] Database check failed: {e}")
        return False

def check_settings():
    """Check important settings."""
    print("\nChecking settings...")
    try:
        from django.conf import settings
        
        checks = [
            ("DEBUG mode", settings.DEBUG, "Debug should be True for development"),
            ("Secret key", settings.SECRET_KEY and len(settings.SECRET_KEY) > 20, "Secret key should be set"),
            ("Installed apps", 'transcriber' in settings.INSTALLED_APPS, "Transcriber app should be installed"),
            ("Celery broker", hasattr(settings, 'CELERY_BROKER_URL'), "Celery broker URL should be set"),
        ]
        
        all_ok = True
        for name, condition, message in checks:
            if condition:
                print(f"[OK] {name}: OK")
            else:
                print(f"[FAIL] {name}: {message}")
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"[FAIL] Settings check failed: {e}")
        return False

def check_api_client():
    """Check API client initialization."""
    print("\nChecking API client...")
    try:
        from transcriber.api_client import APIClient
        
        client = APIClient()
        print(f"[OK] API client initialized (provider: {client.provider})")
        
        # Test cost estimation (should work without API keys)
        try:
            cost = client.estimate_cost_from_text("Sample text for testing", "concise")
            print(f"[OK] Cost estimation works: ${cost:.6f}")
        except Exception as e:
            print(f"[WARN] Cost estimation warning: {e}")
        
        return True
    except Exception as e:
        print(f"[FAIL] API client check failed: {e}")
        return False

def check_templates():
    """Check that templates exist."""
    print("\nChecking templates...")
    try:
        from django.template.loader import get_template
        
        templates = [
            'transcriber/base.html',
            'transcriber/home.html',
            'transcriber/upload.html',
            'transcriber/list.html',
            'transcriber/detail.html',
        ]
        
        all_ok = True
        for template_name in templates:
            try:
                template = get_template(template_name)
                print(f"[OK] Template found: {template_name}")
            except Exception as e:
                print(f"[FAIL] Template missing: {template_name} - {e}")
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"[FAIL] Template check failed: {e}")
        return False

def check_urls():
    """Check that URLs are configured."""
    print("\nChecking URLs...")
    try:
        from django.urls import reverse, NoReverseMatch
        
        urls = [
            ('home', 'transcriber:home'),
            ('upload', 'transcriber:upload'),
            ('list', 'transcriber:recording_list'),
            ('admin', 'admin:index'),
        ]
        
        all_ok = True
        for name, url_name in urls:
            try:
                reverse(url_name)
                print(f"[OK] URL configured: {name} ({url_name})")
            except NoReverseMatch:
                print(f"[FAIL] URL not configured: {name} ({url_name})")
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"[FAIL] URL check failed: {e}")
        return False

def check_celery():
    """Check Celery configuration."""
    print("\nChecking Celery...")
    try:
        from celery import current_app
        
        if hasattr(current_app.conf, 'broker_url'):
            broker = current_app.conf.broker_url
            print(f"[OK] Celery broker configured: {broker}")
            
            if broker == 'memory://':
                print("  Using memory broker (development mode)")
            elif broker.startswith('redis://'):
                print("  Using Redis broker")
            else:
                print(f"  Using custom broker: {broker}")
            
            return True
        else:
            print("[FAIL] Celery broker not configured")
            return False
    except Exception as e:
        print(f"[FAIL] Celery check failed: {e}")
        return False

def main():
    """Run all verification checks."""
    print("=" * 70)
    print("Audio Summarizer - Installation Verification")
    print("=" * 70)
    
    results = []
    
    # Run checks
    results.append(("Database", check_database()))
    results.append(("Settings", check_settings()))
    results.append(("API Client", check_api_client()))
    results.append(("Templates", check_templates()))
    results.append(("URLs", check_urls()))
    results.append(("Celery", check_celery()))
    
    # Summary
    print("\n" + "=" * 70)
    print("Verification Summary:")
    print("=" * 70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for check_name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status}: {check_name}")
    
    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n[SUCCESS] All checks passed!")
        print("\nThe audio summarizer application is ready to use.")
        print("\nNext steps:")
        print("1. Add valid API keys to .env file:")
        print("   - OPENAI_API_KEY for OpenAI/Whisper")
        print("   - DEEPSEEK_API_KEY for DeepSeek")
        print("2. Visit http://localhost:8000/ to use the application")
        print("3. Login with superuser credentials to upload audio files")
        print("4. For production, set DEBUG=False and configure proper security")
    elif passed >= total * 0.7:
        print("\n[WARNING] Some checks failed but core functionality should work")
        print("\nThe application is mostly functional. Issues found:")
        for check_name, success in results:
            if not success:
                print(f"  - {check_name} check failed")
    else:
        print("\n[CRITICAL] Multiple checks failed")
        print("\nThe application may not work correctly. Please fix the issues above.")
    
    return passed == total

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)