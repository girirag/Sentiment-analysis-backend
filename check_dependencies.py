"""Check if all required dependencies are installed"""
import sys

def check_dependencies():
    """Check if all required packages are installed"""
    print("Checking dependencies...\n")
    
    required_packages = {
        'fastapi': 'FastAPI',
        'uvicorn': 'Uvicorn',
        'firebase_admin': 'Firebase Admin SDK',
        'celery': 'Celery',
        'redis': 'Redis',
        'ffmpeg': 'FFmpeg Python',
        'whisper': 'OpenAI Whisper',
        'transformers': 'Transformers',
        'torch': 'PyTorch',
        'sklearn': 'Scikit-learn',
        'pydantic': 'Pydantic',
    }
    
    missing = []
    installed = []
    
    for package, name in required_packages.items():
        try:
            __import__(package)
            installed.append(name)
            print(f"✓ {name}")
        except ImportError:
            missing.append(name)
            print(f"✗ {name} - NOT INSTALLED")
    
    print(f"\n{'='*60}")
    print(f"Installed: {len(installed)}/{len(required_packages)}")
    
    if missing:
        print(f"\n❌ Missing packages:")
        for pkg in missing:
            print(f"  - {pkg}")
        print(f"\nTo install missing packages:")
        print(f"  pip install -r requirements.txt")
        return False
    else:
        print(f"\n✅ All dependencies are installed!")
        return True


def check_system_dependencies():
    """Check system-level dependencies"""
    print(f"\n{'='*60}")
    print("Checking system dependencies...\n")
    
    import subprocess
    import shutil
    
    # Check FFmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f"✓ FFmpeg found at: {ffmpeg_path}")
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
            version_line = result.stdout.split('\n')[0]
            print(f"  {version_line}")
        except:
            pass
    else:
        print(f"✗ FFmpeg - NOT FOUND")
        print(f"  Please install FFmpeg: https://ffmpeg.org/download.html")
        return False
    
    return True


if __name__ == "__main__":
    deps_ok = check_dependencies()
    sys_ok = check_system_dependencies()
    
    print(f"\n{'='*60}")
    if deps_ok and sys_ok:
        print("✅ All checks passed! You're ready to run the backend.")
        print("\nNext steps:")
        print("  1. Configure Firebase credentials (firebase-key.json)")
        print("  2. Update .env file with your settings")
        print("  3. Run: uvicorn app.main:app --reload")
        sys.exit(0)
    else:
        print("❌ Some dependencies are missing. Please install them first.")
        sys.exit(1)
