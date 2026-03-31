#!/usr/bin/env python
"""
Script to check current environment and provide restart instructions.
"""
import os
import sys
import subprocess
import time

def check_current_env():
    """Check current environment variables."""
    print("Checking current environment...")
    
    # Read .env file
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(env_path):
        print(f"ERROR: .env file not found at {env_path}")
        return False
    
    with open(env_path, 'r') as f:
        env_content = f.read()
    
    # Extract OPENAI_API_KEY from .env
    env_key = None
    for line in env_content.split('\n'):
        if line.strip().startswith('OPENAI_API_KEY='):
            env_key = line.split('=', 1)[1].strip()
            if env_key.startswith('"') and env_key.endswith('"'):
                env_key = env_key[1:-1]
            elif env_key.startswith("'") and env_key.endswith("'"):
                env_key = env_key[1:-1]
            break
    
    if not env_key:
        print("ERROR: OPENAI_API_KEY not found in .env file")
        return False
    
    print(f"OPENAI_API_KEY in .env file: {env_key[:30]}...")
    print(f"Key length: {len(env_key)} characters")
    
    # Check if it's still the placeholder
    if env_key == 'sk-your-actual-openai-api-key-here':
        print("\n[WARNING] OPENAI_API_KEY is still the placeholder!")
        print("You need to replace it with your actual OpenAI API key.")
        print("Follow the instructions in API_KEY_SETUP.md")
        return False
    elif 'your-' in env_key.lower():
        print("\n[WARNING] Key appears to contain placeholder text")
        print("Make sure you've replaced the entire placeholder with your actual key")
        return False
    
    print("\n[OK] OPENAI_API_KEY in .env file looks like a real key (not a placeholder)")
    return True

def main():
    print("=" * 60)
    print("Django Server Restart Helper")
    print("=" * 60)
    
    # Check environment
    if not check_current_env():
        print("\nPlease fix the .env file first, then restart the server.")
        return 1
    
    print("\n" + "=" * 60)
    print("SERVER RESTART INSTRUCTIONS:")
    print("=" * 60)
    print("\nThe Django server needs to be restarted to pick up the new .env file.")
    print("\nTo restart:")
    print("1. Press Ctrl+C in the terminal where the server is running")
    print("2. Wait for it to stop completely")
    print("3. Run: python manage.py runserver")
    print("\nOr, if you want to restart automatically:")
    print("1. Close the current terminal window")
    print("2. Open a new terminal")
    print("3. Run: cd audio_summarizer && python manage.py runserver")
    
    print("\n" + "=" * 60)
    print("AFTER RESTARTING:")
    print("=" * 60)
    print("1. Test the API key: python test_api_key.py")
    print("2. Try uploading a new audio file")
    print("3. Check logs/django.log for any errors")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())