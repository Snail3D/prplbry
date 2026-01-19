"""
PRD Creator Configuration
SEC-001: Set up secret key and security configuration
"""
import os
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
