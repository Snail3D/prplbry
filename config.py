"""
PRD Creator Configuration
SEC-001: Set up secret key and security configuration
"""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# SECURITY - FAIL FAST IF MISSING
# ============================================================================
if not os.getenv("SECRET_KEY"):
    raise RuntimeError(
        "SECRET_KEY not set! Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )

SECRET_KEY = os.getenv("SECRET_KEY")

# ============================================================================
# FLASK CONFIGURATION
# ============================================================================
FLASK_ENV = os.getenv("FLASK_ENV", "production")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
DEBUG = FLASK_DEBUG
TESTING = FLASK_ENV == "testing"

# Session cookie security
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS-only in production
SESSION_COOKIE_HTTPONLY = True     # Prevent JavaScript access
SESSION_COOKIE_SAMESITE = "Lax"    # CSRF protection
PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

# ============================================================================
# LLM CONFIGURATION
# ============================================================================
# Ollama (Local LLaMA)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# ============================================================================
# OCR CONFIGURATION
# ============================================================================
TESSERACT_PATH = os.getenv("TESSERACT_PATH", "/usr/bin/tesseract")

# ============================================================================
# APPLICATION SETTINGS
# ============================================================================
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10485760))  # 10MB

# Data storage
BASE_DIR = Path(__file__).parent
PRD_STORAGE_PATH = BASE_DIR / os.getenv("PRD_STORAGE_PATH", "./prd_data")
PRD_STORAGE_PATH.mkdir(exist_ok=True)

# Upload settings
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "gif"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

# ============================================================================
# RATE LIMITING
# ============================================================================
RATE_LIMIT_PRD = os.getenv("RATE_LIMIT_PRD", "10 per minute")
RATE_LIMIT_OCR = os.getenv("RATE_LIMIT_OCR", "100 per hour")
RATE_LIMIT_STORAGE_URI = "memory://" if DEBUG else "redis://localhost:6379"

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================
CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")
CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_DEFAULT_TIMEOUT", 86400))  # 24 hours

# ============================================================================
# INPUT VALIDATION
# ============================================================================
MAX_PROJECT_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 1000
MAX_PROMPT_LENGTH = 10000
ALLOWED_PROJECT_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")

# ============================================================================
# PROMPT TEMPLATES
# ============================================================================
PRD_GENERATION_PROMPT = """You are Ralph Mode PRD Creator. Generate a complete Ralph Mode PRD based on the user's input.

OUTPUT FORMAT (JSON only, no markdown):
{{
  "pn": "project_name",
  "pd": "project_description",
  "sp": "starter_prompt_with_complete_build_instructions",
  "ts": {{"lang": "Python", "fw": "Flask", "db": "PostgreSQL", "oth": ["Redis", "Celery"]}},
  "fs": ["file1.py", "file2.py", "templates/index.html"],
  "p": {{
    "00_security": {{"n": "Security", "t": [
      {{"id": "SEC-001", "ti": "task_title", "d": "task_description", "f": "file.py", "pr": "critical"}}
    ]}},
    "01_setup": {{"n": "Setup", "t": []}},
    "02_core": {{"n": "Core", "t": []}},
    "03_api": {{"n": "API", "t": []}},
    "04_test": {{"n": "Testing", "t": []}}
  }}
}}

TASK GENERATION RULES:
- Generate {task_count} tasks total across all 5 categories
- Always include security tasks in 00_security
- Priority levels: critical, high, medium, low
- Each task must have: id, title, description, file, priority
- Task IDs: SEC-XXX, SET-XXX, CORE-XXX, API-XXX, TEST-XXX

User Input:
- Project Name: {project_name}
- Description: {description}
- Starter Idea: {starter_prompt}
- Tech Stack: {tech_stack}
- Task Count: {task_count}

Generate the complete PRD JSON now."""

# ============================================================================
# TROUBLESHOOTING
# ============================================================================
def validate_environment():
    """Validate that required dependencies are available."""
    errors = []

    # Check Ollama availability
    try:
        import requests
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if response.status_code != 200:
            errors.append(f"Ollama not responding at {OLLAMA_URL}")
    except Exception as e:
        errors.append(f"Ollama connection failed: {e}")

    # Check Tesseract availability
    try:
        import shutil
        if not shutil.which("tesseract"):
            errors.append("Tesseract OCR not found. Install from: https://github.com/tesseract-ocr/tesseract")
    except Exception as e:
        errors.append(f"Tesseract check failed: {e}")

    return errors


if __name__ == "__main__":
    # Validate environment on startup
    errors = validate_environment()
    if errors:
        print("⚠️  Environment warnings:")
        for error in errors:
            print(f"  - {error}")
        print("\nYou can continue, but some features may not work.")
    else:
        print("✓ Environment validated successfully")
