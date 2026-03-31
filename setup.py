#!/usr/bin/env python
"""
Setup script for Audio Summarizer project.
This script helps initialize the project for development or production.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def run_command(command, description):
    """Run a shell command with error handling."""
    print(f"\n{description}...")
    print(f"Command: {command}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ Success: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error: {e.stderr}")
        return False


def setup_environment():
    """Setup the project environment."""
    print_header("Setting up Audio Summarizer Project")
    
    # Check Python version
    if sys.version_info < (3, 10):
        print("✗ Python 3.10 or higher is required")
        return False
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    # Create virtual environment
    venv_path = Path("venv")
    if not venv_path.exists():
        if not run_command("python -m venv venv", "Creating virtual environment"):
            return False
    else:
        print("✓ Virtual environment already exists")
    
    # Install dependencies
    if not run_command("venv\\Scripts\\pip install -r requirements.txt" if os.name == 'nt' else "venv/bin/pip install -r requirements.txt", 
                      "Installing dependencies"):
        return False
    
    # Create .env file from example
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if not env_file.exists():
        if env_example.exists():
            shutil.copy(env_example, env_file)
            print("✓ Created .env file from .env.example")
            print("⚠️  Please edit .env file with your API keys and configuration")
        else:
            print("✗ .env.example not found")
            return False
    else:
        print("✓ .env file already exists")
    
    return True


def setup_database():
    """Setup the database."""
    print_header("Setting up Database")
    
    # Run migrations
    if not run_command("venv\\Scripts\\python manage.py migrate" if os.name == 'nt' else "venv/bin/python manage.py migrate", 
                      "Running database migrations"):
        return False
    
    # Create superuser (optional)
    create_superuser = input("\nCreate superuser? (y/n): ").lower().strip()
    if create_superuser == 'y':
        if not run_command("venv\\Scripts\\python manage.py createsuperuser" if os.name == 'nt' else "venv/bin/python manage.py createsuperuser", 
                          "Creating superuser"):
            print("⚠️  Superuser creation failed or cancelled")
    
    return True


def collect_static_files():
    """Collect static files."""
    print_header("Collecting Static Files")
    
    if not run_command("venv\\Scripts\\python manage.py collectstatic --noinput" if os.name == 'nt' else "venv/bin/python manage.py collectstatic --noinput", 
                      "Collecting static files"):
        return False
    
    return True


def create_directories():
    """Create necessary directories."""
    print_header("Creating Directories")
    
    directories = [
        "media/audio",
        "logs",
        "static",
        "staticfiles",
    ]
    
    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"✓ Created directory: {directory}")
        else:
            print(f"✓ Directory exists: {directory}")
    
    return True


def test_setup():
    """Test the setup."""
    print_header("Testing Setup")
    
    # Run the test script
    test_script = Path("test_setup.py")
    if test_script.exists():
        if not run_command("venv\\Scripts\\python test_setup.py" if os.name == 'nt' else "venv/bin/python test_setup.py", 
                          "Running setup tests"):
            print("⚠️  Setup tests failed, but continuing...")
            return True
    else:
        print("⚠️  test_setup.py not found, skipping tests")
    
    return True


def print_next_steps():
    """Print next steps for the user."""
    print_header("Setup Complete! Next Steps")
    
    print("\n1. Configure your environment:")
    print("   - Edit the .env file with your API keys:")
    print("     * OPENAI_API_KEY (from https://platform.openai.com/api-keys)")
    print("     * DEEPSEEK_API_KEY (optional, from https://platform.deepseek.com)")
    print("     * Update other settings as needed")
    
    print("\n2. Start Redis (required for Celery):")
    print("   Using Docker:")
    print("     docker run -d -p 6379:6379 redis")
    print("   Or install Redis locally")
    
    print("\n3. Start the services in separate terminals:")
    print("   Terminal 1 - Django:")
    print("     venv\\Scripts\\python manage.py runserver" if os.name == 'nt' else "     venv/bin/python manage.py runserver")
    print("   Terminal 2 - Celery Worker:")
    print("     venv\\Scripts\\celery -A audio_summarizer worker --loglevel=info" if os.name == 'nt' else "     venv/bin/celery -A audio_summarizer worker --loglevel=info")
    print("   Terminal 3 - Celery Beat (optional):")
    print("     venv\\Scripts\\celery -A audio_summarizer beat --loglevel=info" if os.name == 'nt' else "     venv/bin/celery -A audio_summarizer beat --loglevel=info")
    
    print("\n4. Access the application:")
    print("   - Web Interface: http://localhost:8000")
    print("   - Admin Panel: http://localhost:8000/admin")
    print("   - API: http://localhost:8000/api/")
    
    print("\n5. For production deployment:")
    print("   - Set DEBUG=False in .env")
    print("   - Generate a new SECRET_KEY")
    print("   - Configure ALLOWED_HOSTS")
    print("   - Use PostgreSQL instead of SQLite")
    print("   - Use cloud storage for media files")
    print("   - Configure HTTPS")
    
    print("\nNeed help? Check the README.md file for detailed documentation.")


def main():
    """Main setup function."""
    try:
        # Change to project directory
        project_root = Path(__file__).parent
        os.chdir(project_root)
        
        print(f"Project directory: {project_root}")
        
        # Run setup steps
        steps = [
            ("Environment setup", setup_environment),
            ("Creating directories", create_directories),
            ("Database setup", setup_database),
            ("Static files", collect_static_files),
            ("Testing", test_setup),
        ]
        
        all_success = True
        for step_name, step_func in steps:
            if not step_func():
                print(f"\n⚠️  {step_name} failed or had issues")
                continue_option = input("Continue anyway? (y/n): ").lower().strip()
                if continue_option != 'y':
                    all_success = False
                    break
        
        if all_success:
            print_next_steps()
            return 0
        else:
            print("\n❌ Setup failed or was cancelled.")
            return 1
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())