"""
Ralph Mode PRD Creator - Main Flask Application

SEC-001: SECRET_KEY validation (via config.py)
SEC-002: OCR Configuration (DEPRECATED - text-only mode)
SEC-003: LLaMA Model Initialization (via prd_engine.py)
X-910/X-1000: Input Validation
X-911/X-1001: Rate Limiting
API-001: API endpoint for PRD creation
"""
import os
import platform
import subprocess
import tempfile
import json
import logging
from io import BytesIO
from functools import wraps
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timedelta
from langdetect import detect, LangDetectException

from flask import (
    Flask, render_template, request, jsonify, Response,
    session, redirect, url_for, flash
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_session import Session
from werkzeug.utils import secure_filename
import redis

from config import (
    SECRET_KEY, DEBUG, ALLOWED_PROJECT_NAME_CHARS,
    MAX_PROJECT_NAME_LENGTH, MAX_DESCRIPTION_LENGTH,
    MAX_PROMPT_LENGTH, PRD_STORAGE_PATH, UPLOAD_FOLDER,
    OLLAMA_URL, OLLAMA_MODEL
)
from exceptions import (
    PRDCreatorError, ValidationError,
    PRDGenerationError, RateLimitError, handle_error
)
from prd_engine import get_prd_engine
from prd_store import get_prd_store, PRD
# OCR removed - text-only mode
# from ocr_processor import get_ocr_processor
import ralph
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO if DEBUG else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TERMINAL LAUNCHING - Cross-platform
# ============================================================================

def get_platform():
    """Get the current platform."""
    system = platform.system()
    if system == 'Darwin':
        return 'macos'
    elif system == 'Linux':
        return 'linux'
    elif system == 'Windows':
        return 'windows'
    return 'unknown'


def launch_terminal_with_prd(prd_content: str, folder: str, cloud_provider: str = 'claude',
                             glm_api_key: str = None, command: str = 'claude',
                             env_file_created: bool = False) -> bool:
    """
    Launch a terminal with PRD pre-fed into Claude/GLM session.

    Args:
        prd_content: The PRD content to feed into the session
        folder: Working directory path
        cloud_provider: 'claude' or 'glm'
        glm_api_key: GLM API key if using glm provider
        command: Command to run (claude, etc.)

    Returns:
        True if successful, False otherwise
    """
    try:
        current_platform = get_platform()
        folder_path = Path(folder).expanduser()

        # Ensure folder exists
        folder_path.mkdir(parents=True, exist_ok=True)

        # Create per-session config file
        session_config = {}
        if cloud_provider == 'glm' and glm_api_key:
            session_config = {
                "provider": "glm",
                "apiKey": glm_api_key,
                "apiUrl": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "model": "glm-4-plus"
            }
        elif cloud_provider == 'claude':
            session_config = {
                "provider": "claude",
                "apiUrl": "https://api.anthropic.com"
            }

        # Write session config (for documentation, though Claude doesn't read it)
        config_file = folder_path / '.claude-session.json'
        with open(config_file, 'w') as f:
            json.dump(session_config, f, indent=2)

        # Create PRD file
        prd_file = folder_path / 'Ralph_PRD.txt'
        with open(prd_file, 'w') as f:
            f.write(prd_content)

        # Build environment variable overrides for THIS TERMINAL SESSION ONLY
        # This overrides global config without affecting other terminals
        env_exports = ""
        if cloud_provider == 'glm' and glm_api_key:
            # Set GLM env vars for this session only
            env_exports = f'''
export ANTHROPIC_API_KEY="{glm_api_key}"
export CLOUD_API_BASE="https://open.bigmodel.cn/api/paas/v4/chat/completions"
export CLOUD_MODEL="glm-4-plus"
export CLOUD_PROVIDER="glm"
echo "Using GLM 4.7 for this session (overrides global config)"
'''
        elif cloud_provider == 'claude':
            # Explicitly use Claude for this session
            env_exports = '''
export CLOUD_PROVIDER="claude"
unset CLOUD_API_BASE
unset CLOUD_MODEL
echo "Using Claude for this session (global config)"
'''

        # Build automation script with --skip-dangerously flag and "don't ask questions"
        # Add instructions about .env file if it was created
        env_instruction = ""
        if env_file_created:
            env_instruction = '''

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📁 .env file has been created with tracked API keys!"
echo "   Fill in the values before running the application."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
'''

        if current_platform == 'windows':
            # Convert env exports to PowerShell
            ps_env = ""
            if cloud_provider == 'glm' and glm_api_key:
                ps_env = f'''
$env:ANTHROPIC_API_KEY = "{glm_api_key}"
$env:CLOUD_API_BASE = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
$env:CLOUD_MODEL = "glm-4-plus"
$env:CLOUD_PROVIDER = "glm"
Write-Host "Using GLM 4.7 for this session"
'''

            script_content = f'''Set-Location "{folder_path}"
{ps_env}{env_instruction}
echo "PRD loaded. Starting {command}..."
echo "do not ask any questions, just begin" | {command} --skip-dangerously
'''
        else:
            script_content = f'''#!/bin/bash
cd "{folder_path}"
{env_exports}{env_instruction}
echo "PRD loaded. Starting {command}..."
echo "do not ask any questions, just begin" | {command} --skip-dangerously

# Keep terminal open
if command -v $SHELL >/dev/null 2>&1; then
    exec $SHELL
else
    exec bash
fi
'''

        # Create temp script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh' if current_platform != 'windows' else '.bat', delete=False) as f:
            f.write(script_content)
            script_path = f.name

        # Make executable on Unix
        if current_platform != 'windows':
            subprocess.run(['chmod', '+x', script_path])

        if current_platform == 'macos':
            # macOS: Use AppleScript with Terminal.app
            subprocess.Popen([
                'osascript',
                '-e', f'tell application "Terminal"',
                '-e', f'do script "' + script_path + '"',
                '-e', 'activate',
                '-e', 'end tell'
            ])

        elif current_platform == 'linux':
            # Linux: Try various terminal emulators
            terminals = [
                ['gnome-terminal', '--', script_path],
                ['xterm', '-e', script_path],
                ['konsole', '-e', script_path],
                ['xfce4-terminal', '-e', script_path]
            ]

            for term_cmd in terminals:
                try:
                    subprocess.Popen(term_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
                except FileNotFoundError:
                    continue

            # Fallback: run script directly
            subprocess.Popen(script_path, shell=True, cwd=folder_path)

        elif current_platform == 'windows':
            # Windows: Use PowerShell
            subprocess.Popen([
                'powershell',
                '-NoExit',
                '-Command', script_content
            ])

        else:
            # Unknown platform: try direct execution
            subprocess.Popen(script_path, shell=True, cwd=folder_path)

        logger.info(f"Launched terminal for PRD in {folder_path} with {cloud_provider}")
        return True

    except Exception as e:
        logger.error(f"Terminal launch error: {e}")
        return False


# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)

# Initialize rate limiter (X-911/X-1001)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1000 per day", "100 per hour"],
    storage_uri="redis://localhost:6379",
    strategy="fixed-window"
)

# Configure Flask-Session for Redis session storage
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url('redis://localhost:6379')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'prplbry:'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
Session(app)

# Initialize components (prd_engine is lazy-loaded only when needed)
prd_engine = None  # Lazy-loaded on first use
prd_store = get_prd_store()

def get_prd_engine_lazy():
    """Lazy-load prd_engine only when needed (AI PRD generation endpoint)."""
    global prd_engine
    if prd_engine is None:
        prd_engine = get_prd_engine()
    return prd_engine

# ============================================================================
# SESSION MANAGEMENT (Pricing & Task Limits)
# ============================================================================

# In-memory session storage (ephemeral)
sessions = {}

FREE_TASK_LIMIT = 50
UNLOCK_PRICE = 2.00  # $2.00

def get_session(session_id: str) -> dict:
    """Get or create a session."""
    if session_id not in sessions:
        sessions[session_id] = {
            'task_count': 0,
            'is_paid': False,
            'created_at': datetime.utcnow()
        }
    return sessions[session_id]

def increment_task_count(session_id: str) -> dict:
    """Increment task count and return session info."""
    session = get_session(session_id)
    session['task_count'] += 1
    return session

def can_add_task(session_id: str) -> tuple[bool, dict]:
    """Check if user can add more tasks."""
    session = get_session(session_id)
    if session['is_paid']:
        return True, session
    return session['task_count'] < FREE_TASK_LIMIT, session

def unlock_session(session_id: str) -> dict:
    """Unlock a session (after payment)."""
    session = get_session(session_id)
    session['is_paid'] = True
    return session


# ============================================================================
# PRD COPY COUNTER (Track PRDs created, once per session)
# ============================================================================

COUNTER_FILE = Path(__file__).parent / 'prd_counter.txt'
# Track sessions that have already copied (in-memory, resets on restart)
copied_sessions = set()

def get_prd_count() -> int:
    """Get current PRD copy count from file."""
    try:
        if COUNTER_FILE.exists():
            return int(COUNTER_FILE.read_text().strip())
    except:
        pass
    return 0

def increment_prd_count(session_id: str) -> int:
    """
    Increment PRD count if this session hasn't copied yet.
    Uses session_id instead of IP to support mobile users with changing IPs.
    """
    if session_id in copied_sessions:
        return get_prd_count()

    # Add session to tracking set
    copied_sessions.add(session_id)

    # Read current count
    current = get_prd_count()

    # Increment and save
    new_count = current + 1
    try:
        COUNTER_FILE.write_text(str(new_count))
    except Exception as e:
        logger.error(f"Failed to save counter: {e}")

    return new_count


# ============================================================================
# DECORATORS
# ============================================================================

def validate_request(f):
    """
    X-910/X-1000: Validate user input decorator
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Validate JSON content type for POST/PUT
        if request.method in ['POST', 'PUT'] and request.is_json:
            data = request.get_json()

            # Check for potential injection patterns
            for key, value in data.items():
                if isinstance(value, str):
                    # Check for SQL injection patterns
                    sql_patterns = ['--', ';', '/*', '*/', 'xp_', 'sp_']
                    if any(pattern in value.lower() for pattern in sql_patterns):
                        logger.warning(f"Potential SQL injection in {key}")
                        return jsonify(handle_error(ValidationError(
                            "Invalid input detected",
                            field=key
                        ))), 400

                    # Check for XSS patterns
                    xss_patterns = ['<script', 'javascript:', 'onerror=', 'onload=']
                    if any(pattern in value.lower() for pattern in xss_patterns):
                        logger.warning(f"Potential XSS in {key}")
                        return jsonify(handle_error(ValidationError(
                            "Invalid input detected",
                            field=key
                        ))), 400

        return f(*args, **kwargs)
    return decorated_function


def validate_project_name(name: str) -> None:
    """Validate project name."""
    if not name or len(name) > MAX_PROJECT_NAME_LENGTH:
        raise ValidationError(
            f"Project name must be 1-{MAX_PROJECT_NAME_LENGTH} characters",
            field="project_name",
            value=name
        )

    # Check for allowed characters
    invalid_chars = set(name) - ALLOWED_PROJECT_NAME_CHARS
    if invalid_chars:
        raise ValidationError(
            f"Invalid characters in project name: {', '.join(invalid_chars)}",
            field="project_name",
            value=name
        )


def validate_tech_stack(tech_stack: str) -> Dict[str, Any]:
    """Convert tech stack preset to dict."""
    presets = {
        "python-flask": {"lang": "Python", "fw": "Flask", "db": "None", "oth": []},
        "python-fastapi": {"lang": "Python", "fw": "FastAPI", "db": "PostgreSQL", "oth": ["Redis"]},
        "javascript-node": {"lang": "JavaScript", "fw": "Node.js", "db": "MongoDB", "oth": []},
        "rust-axum": {"lang": "Rust", "fw": "Axum", "db": "PostgreSQL", "oth": ["Redis"]},
        "go-gin": {"lang": "Go", "fw": "Gin", "db": "PostgreSQL", "oth": []},
    }

    if tech_stack not in presets:
        raise ValidationError(
            f"Invalid tech stack preset: {tech_stack}",
            field="tech_stack",
            value=tech_stack
        )

    return presets[tech_stack]


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return render_template('base.html', content="<h1 style='color:#00ff00'>404 - NOT FOUND</h1>"), 404


@app.errorhandler(500)
def server_error(error):
    logger.exception("Server error")
    return render_template('base.html', content="<h1 style='color:#ff0000'>500 - SERVER ERROR</h1>"), 500


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify(handle_error(RateLimitError(
        "Rate limit exceeded",
        limit=str(e.description)
    ))), 429


# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def index():
    """Landing page - Full send sauce."""
    prd_count = get_prd_count()
    berry_text = "berry" if prd_count == 1 else "berries"
    return render_template('minimal.html', prd_count=prd_count, berry_text=berry_text)


@app.route('/create')
def create_prd():
    """PRD creation page."""
    return render_template('create.html')


@app.route('/privacy')
def privacy():
    """Privacy policy page."""
    return render_template('privacy.html')


@app.route('/prds')
def list_prds():
    """List all saved PRDs with pagination."""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    offset = (page - 1) * per_page
    prds = prd_store.list_all(limit=per_page, offset=offset)

    total = prd_store.count()
    total_pages = (total + per_page - 1) // per_page

    return render_template('list.html', prds=prds, page=page, total_pages=total_pages)


@app.route('/prd/<prd_id>')
def view_prd(prd_id: str):
    """View a single PRD."""
    try:
        prd = prd_store.load(prd_id)
        return render_template('view.html', prd=prd, prd_dict=prd.to_ralph_format())
    except Exception as e:
        flash(f'PRD not found: {prd_id}', 'error')
        return redirect(url_for('list_prds'))


# ============================================================================
# CHAT ROUTES (Ralph)
# ============================================================================

@app.route('/chat')
def chat_new():
    """Create a new chat session."""
    new_session_id = str(uuid.uuid4())
    return redirect(url_for('chat_session', session_id=new_session_id))


@app.route('/chat/<session_id>')
def chat_session(session_id: str):
    """Chat with Ralph - split view with live PRD editor."""
    chat = ralph.get_chat_session(session_id)
    messages = chat.conversation_state.get("messages", [])

    # Convert messages to format expected by template
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg["role"],
            "content": msg["content"],
            "actions": []  # Actions are generated dynamically
        })

    # Get initial PRD state for the editor
    initial_prd = None
    if chat.get_prd():
        initial_prd = ralph.compress_prd(chat.get_prd())

    # Get all sessions for sidebar
    all_sessions = ralph.list_chat_sessions()

    return render_template('split_chat.html',
                         session_id=session_id,
                         messages=formatted_messages,
                         chats=all_sessions,
                         current_chat_id=session_id,
                         initial_prd=initial_prd)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/status')
def api_status():
    """Get system status."""
    try:
        # Check Ollama availability
        import requests
        ollama_available = False
        try:
            response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=1)
            ollama_available = response.status_code == 200
        except:
            pass

        return jsonify({
            "status": "online",
            "model": OLLAMA_MODEL,
            "model_available": ollama_available,
            "prd_count": prd_store.count()
        })
    except Exception as e:
        return jsonify({
            "status": "online",
            "model": OLLAMA_MODEL,
            "model_available": False,
            "prd_count": prd_store.count(),
            "error": str(e)
        })


def detect_language(text: str) -> str:
    """
    Detect the language of the input text.
    Returns ISO 639-1 language code (e.g., 'en', 'es', 'fr', 'zh').
    Defaults to 'en' if detection fails.
    """
    try:
        # Only detect if there's enough text (min 20 chars)
        if len(text.strip()) < 20:
            return 'en'

        lang = detect(text)
        logger.info(f"Detected language: {lang} for text: {text[:50]}...")
        return lang
    except LangDetectException:
        logger.warning(f"Language detection failed for text: {text[:50]}...")
        return 'en'


@app.route('/api/chat', methods=['POST'])
@limiter.limit("60 per minute")
def api_chat():
    """
    Chat with Ralph API endpoint.

    Handles conversational PRD building with Ralph.
    Returns PRD preview for live editor updates.
    Also handles: gender_toggle, suggestion_id, vote
    """
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        session_id = data.get('session_id', '')
        grok_api_key = data.get('grok_api_key', '')  # User's Groq API key for translation

        # Ralph-specific parameters
        action = data.get('action')
        suggestion_id = data.get('suggestion_id')
        vote = data.get('vote')
        gender_toggle = data.get('gender_toggle')

        if not message and not action and not suggestion_id and not gender_toggle:
            return jsonify({"error": "Message or action is required"}), 400

        # Get or create chat session
        if session_id:
            chat = ralph.get_chat_session(session_id)
        else:
            chat = ralph.get_chat_session(str(uuid.uuid4()))
            session_id = chat.session_id

        # Detect language from user's message (only on first message or if not set)
        if message and not chat.conversation_state.get("language"):
            detected_lang = detect_language(message)
            chat.conversation_state["language"] = detected_lang
            logger.info(f"Set conversation language to: {detected_lang}")

        # Get session info (no limits, just tracking)
        session_info = get_session(session_id)
        task_count = session_info['task_count']

        # Track task additions (for display only, no limits)
        if message and action not in ['generate_prd', 'auto_summarize'] and not suggestion_id and not vote and not gender_toggle and len(message) > 10:
            increment_task_count(session_id)
            task_count = session_info['task_count']

        # Process message/action and get response
        # Ralph returns: (response, suggestions, prd_preview, backroom)
        result = chat.process_message(
            message=message,
            action=action,
            suggestion_id=suggestion_id,
            vote=vote,
            gender_toggle=gender_toggle
        )

        # Handle both old return format and new Ralph format
        if len(result) == 3:
            response_text, actions, prd_preview = result
            backroom = None
            suggestions = []
        elif len(result) == 4:
            response_text, suggestions, prd_preview, backroom = result
            actions = []
        else:
            response_text = result[0] if result else "Something went wrong"
            actions = []
            suggestions = []
            prd_preview = None
            backroom = None

        return jsonify({
            "success": True,
            "session_id": session_id,
            "is_new": len(chat.conversation_state.get("messages", [])) <= 2,
            "message": response_text,
            "actions": actions,
            "suggestions": suggestions,
            "prd_preview": prd_preview,
            "backroom": backroom,
            "has_prd": chat.get_prd() is not None,
            "task_count": task_count,
            "prd_title": chat.generate_prd_title(),  # Short 2-3 word title after step 4+
            "donation_prompt": "DONATION_REQUEST" in response_text,  # Trigger donation modal
            "donation_message": response_text.split("DONATION_REQUEST")[-1].strip() if "DONATION_REQUEST" in response_text else None
        })

    except Exception as e:
        logger.exception("Chat API error")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Something went wrong. Please try again."
        }), 500


@app.route('/api/chat/reset', methods=['POST'])
def api_reset_chat():
    """
    Reset/clear conversation and start fresh.
    Creates a new session and redirects to it.
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')

        # Remove old session from memory
        if session_id and session_id in ralph._sessions:
            del ralph._sessions[session_id]

        # Create new session
        new_session_id = str(uuid.uuid4())

        return jsonify({
            "success": True,
            "new_session_id": new_session_id
        })

    except Exception as e:
        logger.exception("Reset error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/unlock', methods=['POST'])
def api_unlock_session():
    """
    Unlock unlimited tasks for a session (after payment).

    Expected JSON:
    {
        "session_id": "uuid",
        "payment_token": "stripe_payment_token"  # or similar
    }

    Returns:
    {
        "success": true,
        "unlocked": true,
        "task_count": 50,
        "is_paid": true
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')
        payment_token = data.get('payment_token', '')

        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400

        # TODO: Verify payment with Stripe
        # For now, just unlock (we'll add Stripe integration later)
        # if not verify_payment(payment_token):
        #     return jsonify({"error": "Invalid payment token"}), 400

        # Unlock the session
        session = unlock_session(session_id)

        return jsonify({
            "success": True,
            "unlocked": True,
            "task_count": session['task_count'],
            "is_paid": session['is_paid'],
            "message": "🎉 Unlocked! You can now add unlimited tasks to your PRD."
        })

    except Exception as e:
        logger.exception("Unlock error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/session/status', methods=['GET'])
def api_session_status():
    """
    Get session status (task count, payment status, etc).

    Query params:
        session_id: UUID

    Returns:
    {
        "success": true,
        "task_count": 25,
        "is_paid": false,
        "tasks_remaining": 25
    }
    """
    try:
        session_id = request.args.get('session_id', '')
        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400

        session = get_session(session_id)

        response = {
            "success": True,
            "task_count": session['task_count'],
            "is_paid": session['is_paid'],
            "free_limit": FREE_TASK_LIMIT,
            "unlock_price": UNLOCK_PRICE
        }

        if not session['is_paid']:
            response['tasks_remaining'] = max(0, FREE_TASK_LIMIT - session['task_count'])

        return jsonify(response)

    except Exception as e:
        logger.exception("Session status error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/prd/count', methods=['POST'])
def api_prd_count():
    """
    Track PRD copy (one per session).
    Call this when user copies the PRD.
    Uses session_id to support mobile users with changing IPs.

    Expects:
    {
        "session_id": "uuid"
    }

    Returns:
    {
        "success": true,
        "count": 42
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')

        if not session_id:
            return jsonify({"error": "Session ID required"}), 400

        new_count = increment_prd_count(session_id)
        return jsonify({"success": True, "count": new_count})
    except Exception as e:
        logger.exception("PRD count error")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# PRD RESTORE API (Drag & Drop)
# ============================================================================

@app.route('/api/prd/restore', methods=['POST'])
def api_restore_prd():
    """
    Restore a PRD from uploaded file (drag & drop).

    Expects:
    {
        "session_id": "uuid",
        "prd_content": "PRD JSON or text content",
        "filename": "original-filename.txt"
    }

    Returns:
    {
        "success": true,
        "session_id": "uuid",
        "restored": true,
        "was_paid": false
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')
        prd_content = data.get('prd_content', '')

        if not prd_content:
            return jsonify({"error": "PRD content is required"}), 400

        # Check if PRD contains payment marker (to restore paid status)
        was_paid = False
        if 'UNLOCKED_SESSION' in prd_content or 'PAID_SESSION' in prd_content:
            was_paid = True

        # Create or get session
        if not session_id:
            session_id = str(uuid.uuid4())

        session = get_session(session_id)

        # Restore payment status if previously paid
        if was_paid:
            session['is_paid'] = True

        # Parse PRD content and restore to chat session
        try:
            # Try to parse as JSON first
            if prd_content.strip().startswith('{'):
                prd_data = json.loads(prd_content)
                chat = ralph.get_chat_session(session_id)
                # Restore PRD to chat
                chat.restore_prd(prd_data)
            else:
                # Plain text - try to extract JSON if present
                chat = ralph.get_chat_session(session_id)
                # Look for JSON block in the content
                import re
                json_match = re.search(r'\{[\s\S]*\}', prd_content)
                if json_match:
                    prd_data = json.loads(json_match.group())
                    chat.restore_prd(prd_data)
                else:
                    # Just set the content as current PRD
                    chat.set_prd_content(prd_content)

        except Exception as e:
            logger.warning(f"Could not fully restore PRD: {e}")
            # Still return success - we got the content

        return jsonify({
            "success": True,
            "session_id": session_id,
            "restored": True,
            "was_paid": was_paid,
            "task_count": session['task_count'],
            "is_paid": session['is_paid']
        })

    except Exception as e:
        logger.exception("PRD restore error")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# TERMINAL SCRIPT API
# ============================================================================

@app.route('/api/terminal/script', methods=['POST'])
def api_generate_terminal_script():
    """
    Generate a downloadable shell script to launch terminal with PRD.
    Expects: {prd_content, folder, cloud_provider, glm_api_key, services, github_url, github_branch, platform}
    """
    try:
        data = request.get_json()

        prd_content = data.get('prd_content', '')
        folder = data.get('folder', '~/my-project')
        cloud_provider = data.get('cloud_provider', 'claude')
        glm_api_key = data.get('glm_api_key', '')
        services = data.get('services', [])
        github_url = data.get('github_url', '')
        github_branch = data.get('github_branch', 'main')
        platform = data.get('platform', 'macos')  # macos, windows, linux

        if not prd_content:
            return jsonify({"error": "prd_content is required"}), 400

        # Generate platform-specific script
        script_result = generate_launch_script(
            prd_content=prd_content,
            folder=folder,
            cloud_provider=cloud_provider,
            glm_api_key=glm_api_key,
            services=services,
            github_url=github_url,
            github_branch=github_branch,
            platform=platform
        )

        return jsonify({
            "success": True,
            "script": script_result['script'],
            "filename": script_result['filename'],
            "instructions": script_result.get('instructions', '')
        })

    except Exception as e:
        logger.exception("Generate script error")
        return jsonify({"error": str(e)}), 500


def generate_launch_script(prd_content: str, folder: str, cloud_provider: str,
                          glm_api_key: str, services: list, github_url: str = '',
                          github_branch: str = 'main', platform: str = 'macos') -> dict:
    """
    Generate a platform-specific shell script for launching terminal with PRD.
    Returns dict with 'script', 'filename', and 'instructions'.
    """

    # Create PRD file content (escaped for heredoc)
    prd_file_content = prd_content

    # Create .env content
    env_content = "# Environment Variables for Project\n"
    env_content += "# Generated by Ralph Mode PRD Creator\n\n"

    if cloud_provider == 'glm' and glm_api_key:
        env_content += f"# Groq API Key (for this session)\nGROQ_API_KEY={glm_api_key}\n\n"

    if services:
        env_content += "# Tracked API Keys (fill these in)\n"
        for service in services:
            env_content += f"# {service['description']}\n{service['env_var']}=\n\n"

    env_content += "# Application Settings\n"
    env_content += "FLASK_ENV=development\n"
    env_content += "DEBUG=True\n"
    env_content += "SECRET_KEY=change-me-in-production\n"

    # GitHub integration section
    github_section = ""
    if github_url:
        github_section = f"""

# GitHub Integration
echo "📦 Setting up GitHub repository..."
if [ -d ".git" ]; then
    echo "Git already initialized"
else
    git init
    git branch -M {github_branch}
fi

# Check if remote exists
if git remote get-url origin >/dev/null 2>&1; then
    echo "Git remote already configured"
else
    git remote add origin {github_url}
    echo "✅ GitHub remote added: {github_url}"
fi

echo ""
echo "💡 To push to GitHub later, run:"
echo "   git add ."
echo "   git commit -m 'Initial commit from Ralph Mode PRD'"
echo "   git push -u origin {github_branch}"
echo ""
"""

    # Generate platform-specific script
    if platform == 'windows':
        script = generate_windows_script(prd_file_content, env_content, folder,
                                        cloud_provider, glm_api_key, github_section)
        filename = "launch-ralph-prd.ps1"
        instructions = "1. Download the PowerShell script\n2. Right-click and select 'Run with PowerShell'\n3. If prompted, allow script execution"
    else:  # macos or linux
        script = generate_unix_script(prd_file_content, env_content, folder,
                                     cloud_provider, glm_api_key, github_section)
        filename = "launch-ralph-prd.sh"
        instructions = "1. Download the shell script\n2. Open terminal and run: chmod +x launch-ralph-prd.sh\n3. Run: ./launch-ralph-prd.sh"

    return {
        'script': script,
        'filename': filename,
        'instructions': instructions
    }


def generate_unix_script(prd_content: str, env_content: str, folder: str,
                        cloud_provider: str, glm_api_key: str, github_section: str) -> str:
    """Generate Unix (macOS/Linux) shell script"""

    script = f'''#!/bin/bash
# =============================================================================
# Ralph Mode PRD - Terminal Launch Script (macOS/Linux)
# Generated by Ralph Mode PRD Creator
# =============================================================================

set -e  # Exit on error

PROJECT_DIR="{folder}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Ralph Mode PRD Launcher"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create project directory
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "📁 Project folder: $PROJECT_DIR"
echo ""

# Create .env file
cat > .env << 'ENVEOF'
{env_content}
ENVEOF

echo "✅ .env file created"
echo ""

# Create PRD file
cat > Ralph_PRD.txt << 'PRDEOF'
{prd_content}
PRDEOF

echo "✅ PRD file created (Ralph_PRD.txt)"
echo ""

# Create .gitignore
cat > .gitignore << 'GITEOF'
.env
.venv/
__pycache__/
*.pyc
.pytest_cache.py
.coverage
node_modules/
.DS_Store
*.log
GITEOF

echo "✅ .gitignore created"
echo ""
'''

    # Add environment setup
    if cloud_provider == 'glm' and glm_api_key:
        script += f'''
# Groq Configuration for this session
export GROQ_API_KEY="{glm_api_key}"
export ANTHROPIC_API_KEY="{glm_api_key}"
export CLOUD_API_BASE="https://api.groq.com/openai/v1"
export CLOUD_MODEL="llama-3.3-70b-versatile"
export CLOUD_PROVIDER="groq"

echo "🔑 Using Groq API"
echo ""
'''

    # Add GitHub section if provided
    if github_section:
        script += github_section

    script += '''
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 Starting Claude with PRD..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Feeding PRD to Claude and starting session..."
echo ""

# Feed the PRD to Claude and start working
echo "do not ask any questions, just begin" | claude --skip-dangerously

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Session complete! Terminal will stay open."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Keep terminal open
if command -v $SHELL >/dev/null 2>&1; then
    exec $SHELL
else
    exec bash
fi
'''

    return script


def generate_windows_script(prd_content: str, env_content: str, folder: str,
                           cloud_provider: str, glm_api_key: str, github_section: str) -> str:
    """Generate Windows PowerShell script"""

    # Escape PowerShell special characters
    env_escaped = env_content.replace('"', '`"').replace('$', '`$').replace('`', '``')
    prd_escaped = prd_content.replace('"', '`"').replace('$', '`$').replace('`', '``')

    script = f'''# =============================================================================
# Ralph Mode PRD - Terminal Launch Script (Windows PowerShell)
# Generated by Ralph Mode PRD Creator
# =============================================================================

$ErrorActionPreference = "Stop"

$PROJECT_DIR = "{folder}"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "🚀 Ralph Mode PRD Launcher" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Create project directory
New-Item -ItemType Directory -Force -Path $PROJECT_DIR | Out-Null
Set-Location $PROJECT_DIR

Write-Host "📁 Project folder: $PROJECT_DIR" -ForegroundColor Yellow
Write-Host ""

# Create .env file
@"
{env_content}
"@ | Out-File -FilePath ".env" -Encoding UTF8

Write-Host "✅ .env file created" -ForegroundColor Green
Write-Host ""

# Create PRD file
@"
{prd_content}
"@ | Out-File -FilePath "Ralph_PRD.txt" -Encoding UTF8

Write-Host "✅ PRD file created (Ralph_PRD.txt)" -ForegroundColor Green
Write-Host ""

# Create .gitignore
@"
.env
.venv/
__pycache__/
*.pyc
.pytest_cache.py
.coverage
node_modules/
.DS_Store
*.log
"@ | Out-File -FilePath ".gitignore" -Encoding UTF8

Write-Host "✅ .gitignore created" -ForegroundColor Green
Write-Host ""
'''

    # Add environment setup
    if cloud_provider == 'glm' and glm_api_key:
        script += f'''
# Groq Configuration for this session
$env:GROQ_API_KEY = "{glm_api_key}"
$env:ANTHROPIC_API_KEY = "{glm_api_key}"
$env:CLOUD_API_BASE = "https://api.groq.com/openai/v1"
$env:CLOUD_MODEL = "llama-3.3-70b-versatile"
$env:CLOUD_PROVIDER = "groq"

Write-Host "🔑 Using Groq API" -ForegroundColor Yellow
Write-Host ""
'''

    # Add GitHub section for PowerShell (converted from bash to PowerShell)
    if github_section:
        # Convert bash commands to PowerShell
        github_ps = github_section.replace('echo "', 'Write-Host "')
        github_ps = github_ps.replace('echo "   ', 'Write-Host "   ')
        github_ps = github_ps.replace('""', '"')
        github_ps = github_ps.replace('if [ -d ".git" ]; then', 'if (Test-Path ".git") {')
        github_ps = github_ps.replace('else', '} else {')
        github_ps = github_ps.replace('fi', '}')
        github_ps = github_ps.replace('git branch -M', 'git branch -M')
        script += github_ps

    script += '''
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "🎯 Starting Claude with PRD..." -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "Feeding PRD to Claude and starting session..." -ForegroundColor Yellow
Write-Host ""

# Feed the PRD to Claude and start working
"do not ask any questions, just begin" | claude --skip-dangerously

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "✨ Session complete!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Enter to exit..." -ForegroundColor Gray
Read-Host
'''

    return script

    return script


# ============================================================================
# SAVE/LOAD CONVERSATION API
# ============================================================================

@app.route('/api/conversations/save', methods=['POST'])
def api_save_conversation():
    """
    Save the current conversation state to a file.
    Expects: {session_id: str, name: str (optional)}
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')
        name = data.get('name')

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        chat = ralph.get_chat_session(session_id)
        result = chat.save_conversation(name)

        return jsonify(result)

    except Exception as e:
        logger.exception("Save conversation error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversations/list', methods=['GET'])
def api_list_conversations():
    """
    List all saved conversations.
    """
    try:
        conversations = ralph.RalphChat.list_saved_conversations()
        return jsonify({
            "success": True,
            "conversations": conversations
        })

    except Exception as e:
        logger.exception("List conversations error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversations/load', methods=['POST'])
def api_load_conversation():
    """
    Load a saved conversation and restore full state.
    Expects: {filename: str}
    Returns: {success: bool, session_id: str, messages: [...], prd: {...}}
    """
    try:
        data = request.get_json()
        filename = data.get('filename', '')

        if not filename:
            return jsonify({"error": "filename is required"}), 400

        chat = ralph.RalphChat.load_conversation(filename)

        return jsonify({
            "success": True,
            "session_id": chat.session_id,
            "messages": chat.conversation_state.get("messages", []),
            "prd": chat.conversation_state.get("prd", {}),
            "backroom": chat.conversation_state.get("backroom", []),
            "step": chat.conversation_state.get("step", 0),
            "gender": chat.conversation_state.get("gender", "male")
        })

    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.exception("Load conversation error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversations/delete', methods=['POST'])
def api_delete_conversation():
    """
    Delete a saved conversation.
    Expects: {filename: str}
    """
    try:
        data = request.get_json()
        filename = data.get('filename', '')

        if not filename:
            return jsonify({"error": "filename is required"}), 400

        success = ralph.RalphChat.delete_saved_conversation(filename)

        return jsonify({
            "success": success,
            "message": "Deleted" if success else "File not found"
        })

    except Exception as e:
        logger.exception("Delete conversation error")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# SERVICES TRACKER API
# ============================================================================

@app.route('/api/services/tracked', methods=['GET'])
def api_get_tracked_services():
    """
    Get list of tracked services that need API keys based on conversation.
    Query param: session_id
    """
    try:
        session_id = request.args.get('session_id', '')
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        chat = ralph.get_chat_session(session_id)
        services = chat._extract_services_from_conversation()

        return jsonify({
            "success": True,
            "services": services,
            "count": len(services)
        })

    except Exception as e:
        logger.exception("Get tracked services error")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# TERMINAL LAUNCH API
# ============================================================================

@app.route('/api/terminal/launch', methods=['POST'])
def api_launch_terminal():
    """
    Launch a terminal with the PRD pre-fed into Claude/GLM.
    Creates .env file with tracked API keys.

    Expects: {
        prd_content: str,
        folder: str,
        cloud_provider: str (claude|glm),
        glm_api_key: str (optional),
        command: str (default: claude),
        session_id: str (optional, for service tracking)
    }
    """
    try:
        data = request.get_json()

        prd_content = data.get('prd_content', '')
        folder = data.get('folder', '')
        cloud_provider = data.get('cloud_provider', 'claude')
        glm_api_key = data.get('glm_api_key', '')
        command = data.get('command', 'claude')
        session_id = data.get('session_id', '')

        if not prd_content:
            return jsonify({"error": "prd_content is required"}), 400

        if not folder:
            return jsonify({"error": "folder is required"}), 400

        # Get tracked services and create .env file
        tracked_services = []
        env_content = "# Environment Variables for Project\n# Generated by Ralph Mode PRD Creator\n\n"

        if session_id:
            try:
                chat = ralph.get_chat_session(session_id)
                tracked_services = chat._extract_services_from_conversation()

                # Build .env content with tracked services
                for service in tracked_services:
                    env_content += f"# {service['description']}\n"
                    env_content += f"{service['env_var']}=\n\n"
            except Exception as e:
                logger.warning(f"Could not extract services: {e}")

        # Add cloud provider to .env if GLM
        if cloud_provider == 'glm' and glm_api_key:
            env_content += "# GLM 4.7 API Key\n"
            env_content += f"GLM_API_KEY={glm_api_key}\n\n"
            env_content += "# GLM API Endpoint\n"
            env_content += "GLM_API_BASE=https://open.bigmodel.cn/api/paas/v4/chat/completions\n\n"

        # Add common .env entries
        env_content += "# Application Settings\n"
        env_content += "FLASK_ENV=development\n"
        env_content += "DEBUG=True\n"
        env_content += "SECRET_KEY=change-me-in-production\n\n"

        # Write .env file to project folder
        folder_path = Path(folder).expanduser()
        folder_path.mkdir(parents=True, exist_ok=True)

        env_file = folder_path / '.env'
        with open(env_file, 'w') as f:
            f.write(env_content)

        # Create .env.example with only the keys (no values)
        env_example_content = "# Environment Variables Template\n"
        env_example_content += "# Copy this file to .env and fill in the values\n\n"
        if session_id and tracked_services:
            for service in tracked_services:
                env_example_content += f"{service['env_var']}=\n"
        env_example_content += "\n# Application Settings\nSECRET_KEY=\nFLASK_ENV=\n"

        env_example_file = folder_path / '.env.example'
        with open(env_example_file, 'w') as f:
            f.write(env_example_content)

        success = launch_terminal_with_prd(
            prd_content=prd_content,
            folder=folder,
            cloud_provider=cloud_provider,
            glm_api_key=glm_api_key,
            command=command,
            env_file_created=True
        )

        if success:
            return jsonify({
                "success": True,
                "message": f"Terminal launched with PRD in {folder}",
                "env_created": True,
                "tracked_services": tracked_services,
                "env_file_count": len(tracked_services)
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to launch terminal"
            }), 500

    except Exception as e:
        logger.exception("Terminal launch error")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# OLLAMA MODEL MANAGEMENT API
# ============================================================================

@app.route('/api/ollama/models')
def api_ollama_models():
    """Get list of installed Ollama models."""
    try:
        import requests
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)

        if response.status_code == 200:
            data = response.json()
            models = []

            if 'models' in data:
                for model in data['models']:
                    models.append({
                        'name': model['name'],
                        'size': model.get('size', 0),
                        'modified': model.get('modified_at', '')
                    })

            return jsonify({
                "success": True,
                "models": models
            })
        else:
            return jsonify({
                "success": False,
                "error": "Ollama not responding"
            }), 503

    except Exception as e:
        logger.exception("Ollama models error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/ollama/search')
def api_ollama_search():
    """Search for Ollama models in the library."""
    try:
        query = request.args.get('q', '')

        # Ollama library search - using a predefined list of popular models
        # In production, you'd scrape ollama.com/library or use their API
        popular_models = [
            {"name": "llama3.2", "description": "Meta's Llama 3.2 - 3B parameter model"},
            {"name": "llama3.2:1b", "description": "Meta's Llama 3.2 - 1B parameter model (lightweight)"},
            {"name": "llama3.1", "description": "Meta's Llama 3.1 - 8B parameter model"},
            {"name": "llama3", "description": "Meta's Llama 3 - 70B parameter model"},
            {"name": "mistral", "description": "Mistral 7B - high quality open source model"},
            {"name": "mixtral", "description": "Mixtral 8x7B - mixture of experts model"},
            {"name": "codellama", "description": "Code Llama - model fine-tuned for coding"},
            {"name": "deepseek-coder", "description": "DeepSeek Coder - specialized for code"},
            {"name": "phi3", "description": "Microsoft Phi-3 - 3.8B parameter model"},
            {"name": "gemma2", "description": "Google Gemma 2 - lightweight yet powerful"},
            {"name": "qwen2.5", "description": "Alibaba Qwen 2.5 - multilingual model"},
            {"name": "nomic-embed-text", "description": "Nomic embedding model for text"},
        ]

        # Filter by query
        if query:
            filtered = [m for m in popular_models if query.lower() in m['name'].lower()]
        else:
            filtered = popular_models[:10]

        return jsonify({
            "success": True,
            "models": filtered
        })

    except Exception as e:
        logger.exception("Ollama search error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/ollama/pull', methods=['POST'])
@limiter.limit("10 per hour")
def api_ollama_pull():
    """Pull/download an Ollama model."""
    try:
        data = request.get_json()
        model = data.get('model', '')

        if not model:
            return jsonify({"error": "Model name is required"}), 400

        import requests
        # Pull model (this is async, will take time)
        response = requests.post(
            f"{OLLAMA_URL}/api/pull",
            json={"name": model},
            timeout=300  # 5 minute timeout
        )

        if response.status_code == 200:
            return jsonify({
                "success": True,
                "message": f"Model {model} pulled successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to pull model"
            }), 500

    except Exception as e:
        logger.exception("Ollama pull error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# BACKROOM DEBATE API
# ============================================================================

@app.route('/api/backroom/debate', methods=['POST'])
@limiter.limit("20 per hour")
def api_backroom_debate():
    """
    Generate a backroom debate between Stool (skeptic) and Gomer (optimist).
    Returns 10 exchanges (5 each) with typing effect for display.
    """
    try:
        data = request.get_json()
        context = data.get('context', 'Building a web application')

        # Import for LLM calls
        import requests

        # Define analyst personas
        ANALYST_A = {"name": "Stool", "role": "The Skeptic", "emoji": "🤔"}
        ANALYST_B = {"name": "Gomer", "role": "The Optimist", "emoji": "💡"}

        # Build the debate
        exchanges = []

        # First message - Stool starts
        prompt_1 = f"""Stool (skeptic) analyzing project. 1-2 sentences MAX.
CTX: {context}
Question ONE thing: need, problem, or gap. Direct, punchy."""

        response_1 = query_llm(prompt_1)
        if response_1:
            exchanges.append({"analyst": "Stool", "message": response_1})

        # Generate 9 more exchanges (alternating)
        for i in range(9):
            last_msg = exchanges[-1]["message"]

            if i % 2 == 0:  # Gomer's turn
                prompt = f"""Gomer (optimist) responds. 1-2 sentences MAX.
CTX: {context}
STOOL: {last_msg}
Counter with ONE use case or opportunity. Punchy."""
                analyst = "Gomer"
            else:  # Stool's turn
                prompt = f"""Stool (skeptic) responds. 1-2 sentences MAX.
CTX: {context}
GOMER: {last_msg}
ONE concern or edge case. Acknowledge good points briefly."""
                analyst = "Stool"

            response = query_llm(prompt)
            if response:
                exchanges.append({"analyst": analyst, "message": response})

        return jsonify({
            "success": True,
            "debate": exchanges
        })

    except Exception as e:
        logger.exception("Backroom debate error")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def query_llm(prompt: str) -> str:
    """Query the LLM (Ollama or Grok) with a prompt."""
    try:
        import requests

        # Check if Grok API key is configured
        grok_api_key = os.environ.get("GROK_API_KEY") or os.environ.get("GROQ_API_KEY")

        if grok_api_key:
            # Use Grok/Groq
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {grok_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.8,
                        "max_tokens": 150
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()
            except:
                pass  # Fall through to Ollama

        # Use Ollama
        ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.8, "num_predict": 150}
            },
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("response", "").strip()

        return ""

    except Exception as e:
        logger.error(f"LLM query error: {e}")
        return ""


@app.route('/api/chat/backroom-add', methods=['POST'])
def api_backroom_add():
    """Add an approved backroom message to the PRD."""
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')
        analyst = data.get('analyst', '')
        message = data.get('message', '')

        chat = ralph.get_chat_session(session_id)
        prd = chat.get_prd()

        if not prd:
            return jsonify({"success": False, "error": "No PRD yet"}), 400

        # Add as a task based on the analyst's perspective
        task_id = f"BACK-{len(prd.get('p', {}).get('02_core', {}).get('t', [])) + 1}"

        if analyst == 'Stool':
            # Skeptic concerns → Security/Validation tasks
            prd['p']['00_security']['t'].append({
                "id": task_id,
                "ti": f"Address: {message[:50]}",
                "d": f"Security concern from backroom: {message}",
                "f": "security.py",
                "pr": "high"
            })
        else:
            # Optimist suggestions → Feature tasks
            prd['p']['02_core']['t'].append({
                "id": task_id,
                "ti": f"Feature: {message[:50]}",
                "d": f"Feature suggestion from backroom: {message}",
                "f": "features.py",
                "pr": "medium"
            })

        # Update PRD display
        prd_preview = ralph.compress_prd(prd)

        return jsonify({
            "success": True,
            "prd_preview": prd_preview,
            "message": f"*nods* Added {analyst}'s point to your PRD!"
        })

    except Exception as e:
        logger.exception("Backroom add error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/chat/summarize', methods=['POST'])
def api_summarize_prd():
    """Generate a summary and update the PRD."""
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')

        chat = ralph.get_chat_session(session_id)
        prd = chat.get_prd()

        if not prd:
            return jsonify({"success": False, "error": "No PRD yet"}), 400

        # Add summary task
        total_tasks = sum(len(cat.get("t", [])) for cat in prd.get("p", {}).values())

        prd_preview = ralph.compress_prd(prd)

        return jsonify({
            "success": True,
            "prd_preview": prd_preview,
            "total_tasks": total_tasks,
            "message": f"*beams proudly* Your PRD now has {total_tasks} tasks!"
        })

    except Exception as e:
        logger.exception("Summarize error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/chat/<session_id>/export/<format>')
def api_export_chat_prd(session_id: str, format: str):
    """Export PRD from chat session."""
    try:
        chat = ralph.get_chat_session(session_id)
        prd = chat.get_prd()

        if not prd:
            return jsonify({"error": "No PRD generated yet"}), 404

        if format == 'json':
            response = Response(
                json.dumps(prd, indent=2),
                mimetype='application/json',
                headers={
                    'Content-Disposition': f'attachment; filename="prd-{prd.get("pn", "project")}.json"'
                }
            )
            return response

        elif format == 'markdown':
            md = f"# {prd.get('pn', 'Project')}\n\n"
            md += f"**Description:** {prd.get('pd', 'N/A')}\n\n"
            md += f"## Tech Stack\n\n"
            ts = prd.get('ts', {})
            md += f"- Language: {ts.get('lang', 'N/A')}\n"
            md += f"- Framework: {ts.get('fw', 'N/A')}\n"
            md += f"- Database: {ts.get('db', 'N/A')}\n"
            if ts.get('oth'):
                md += f"- Other: {', '.join(ts['oth'])}\n"
            md += f"\n## File Structure\n\n"
            for f in prd.get('fs', []):
                md += f"- `{f}`\n"
            md += f"\n## Tasks\n\n"
            for cat_id, cat in prd.get('p', {}).items():
                md += f"### {cat['n']} [{cat_id}]\n\n"
                for task in cat['t']:
                    md += f"#### {task['id']} [{task['pr']}]\n\n"
                    md += f"**{task['ti']}**\n\n"
                    md += f"- {task['d']}\n"
                    md += f"- File: `{task['f']}`\n\n"

            response = Response(
                md,
                mimetype='text/markdown',
                headers={
                    'Content-Disposition': f'attachment; filename="prd-{prd.get("pn", "project")}.md"'
                }
            )
            return response

        elif format == 'compressed':
            # Return compressed format (like Telegram) - includes full legend
            compressed = ralph.compress_prd(prd)
            response = Response(
                compressed,
                mimetype='text/plain',
                headers={
                    'Content-Disposition': f'attachment; filename="prd-{prd.get("pn", "project")}.txt"'
                }
            )
            return response

        else:
            return jsonify({"error": "Invalid format. Use: json, markdown, or compressed"}), 400

    except Exception as e:
        logger.exception("Export error")
        return jsonify({"error": str(e)}), 500


@app.route('/api/ocr', methods=['POST'])
@limiter.limit("100 per hour")
def api_ocr():
    """
    Extract text from uploaded image using OCR.

    X-911/X-1001: Rate limited to 100 requests per hour
    """
    if 'file' not in request.files:
        return jsonify(handle_error(ValidationError("No file uploaded"))), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify(handle_error(ValidationError("No file selected"))), 400

    try:
        # Read file data
        data = file.read()
        text = get_ocr_processor().extract_from_bytes(data, file.filename)

        return jsonify({
            "success": True,
            "text": text
        })
    except OCRError as e:
        return jsonify(handle_error(e)), 400
    except Exception as e:
        return jsonify(handle_error(e)), 500


@app.route('/api/chat/analyze-image', methods=['POST'])
@limiter.limit("30 per hour")
def api_analyze_image():
    """
    Analyze a dropped image and extract PRD-relevant information.

    Expects JSON with 'image' (base64), 'filename', 'session_id', 'grok_api_key'
    Returns analyzed information to add to PRD.
    """
    try:
        data = request.get_json()

        if not data or 'image' not in data:
            return jsonify({"error": "No image data provided"}), 400

        image_data = data.get('image', '')
        filename = data.get('filename', 'uploaded-image')
        session_id = data.get('session_id')
        api_key = data.get('grok_api_key')

        # Extract base64 data if it has the data URL prefix
        if image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]

        # Decode base64
        import base64
        from io import BytesIO

        image_bytes = base64.b64decode(image_data)
        image_file = BytesIO(image_bytes)
        image_file.name = filename

        # Use OCR to extract text from image
        text = get_ocr_processor().extract_from_bytes(image_bytes, filename)

        if not text or len(text.strip()) < 10:
            return jsonify({
                "error": "Could not extract enough text from image. The image might be unclear or contain no readable text.",
                "message": "*squints at image*\n\nI can see this image, but I'm having trouble reading the text. Could you describe what you'd like me to add?"
            }), 400

        # Get chat session and process the extracted text
        chat = ralph.get_chat_session(session_id)

        # Process as a message asking Ralph to analyze and add features
        response_message, _, prd_preview = chat.process_message(
            f"[Analyzed image: {filename}]\n\nExtracted text:\n{text}\n\nPlease analyze this content and extract any relevant features, requirements, UI elements, or technical details to add to the PRD. Tell me what you found and what you're adding.",
            api_key=api_key
        )

        return jsonify({
            "success": True,
            "message": response_message,
            "prd_preview": prd_preview,
            "extracted_text": text
        })

    except OCRError as e:
        logger.error(f"OCR error in image analysis: {e}")
        return jsonify({
            "error": str(e),
            "message": "*rubs eyes*\n\nMy vision's acting up. Could you describe what's in this image?"
        }), 400
    except Exception as e:
        logger.exception("Image analysis error")
        return jsonify({
            "error": str(e),
            "message": "*looks puzzled*\n\nSomething went wrong analyzing that image. Try describing it instead?"
        }), 500


@app.route('/api/prd/generate', methods=['POST'])
@limiter.limit("10 per minute")  # X-911/X-1001: Rate limiting
@validate_request  # X-910/X-1000: Input validation
def api_generate_prd():
    """
    API-001: API endpoint for PRD creation

    Generates a Ralph Mode PRD based on user input.
    """
    try:
        data = request.get_json()

        # Extract fields
        project_name = data.get('project_name', '').strip()
        description = data.get('description', '').strip()
        starter_prompt = data.get('starter_prompt', '').strip()
        model = data.get('model', OLLAMA_MODEL)
        task_count = data.get('task_count', 34)
        tech_stack_preset = data.get('tech_stack', 'python-flask')

        # Validate inputs
        validate_project_name(project_name)

        if not description or len(description) > MAX_DESCRIPTION_LENGTH:
            raise ValidationError(
                f"Description must be 1-{MAX_DESCRIPTION_LENGTH} characters",
                field="description"
            )

        if not starter_prompt or len(starter_prompt) > MAX_PROMPT_LENGTH:
            raise ValidationError(
                f"Starter prompt must be 1-{MAX_PROMPT_LENGTH} characters",
                field="starter_prompt"
            )

        if task_count < 5 or task_count > 100:
            raise ValidationError(
                "Task count must be between 5 and 100",
                field="task_count",
                value=task_count
            )

        tech_stack = validate_tech_stack(tech_stack_preset)

        # Generate PRD
        logger.info(f"Generating PRD: {project_name} with {model}, {task_count} tasks")
        engine = get_prd_engine_lazy()
        prd_data = engine.generate_prd(
            project_name=project_name,
            description=description,
            starter_prompt=starter_prompt,
            tech_stack=tech_stack,
            task_count=task_count
        )

        # Create PRD object and save
        prd = PRD.from_ralph_format(prd_data)
        prd_id = prd_store.save(prd)

        logger.info(f"PRD generated and saved: {prd_id}")

        return jsonify({
            "success": True,
            "id": prd_id,
            "project_name": prd.project_name,
            "prd": prd_data
        })

    except ValidationError as e:
        return jsonify(handle_error(e)), 400
    except PRDGenerationError as e:
        return jsonify(handle_error(e)), 500
    except Exception as e:
        logger.exception("Unexpected error in PRD generation")
        return jsonify(handle_error(e)), 500


@app.route('/api/prd/<prd_id>', methods=['GET'])
def api_get_prd(prd_id: str):
    """Get a PRD by ID."""
    try:
        prd = prd_store.load(prd_id)
        return jsonify({
            "success": True,
            "prd": prd.to_dict()
        })
    except Exception as e:
        return jsonify(handle_error(e)), 404


@app.route('/api/prd/<prd_id>', methods=['DELETE'])
def api_delete_prd(prd_id: str):
    """Delete a PRD by ID."""
    try:
        if prd_store.delete(prd_id):
            return jsonify({"success": True})
        else:
            return jsonify(handle_error(ValidationError("PRD not found", prd_id=prd_id))), 404
    except Exception as e:
        return jsonify(handle_error(e)), 500


@app.route('/api/prds', methods=['GET'])
def api_list_prds():
    """
    X-941/X-1007: API pagination
    List all PRDs with pagination support.
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    offset = (page - 1) * per_page
    prds = prd_store.list_all(limit=per_page, offset=offset)

    total = prd_store.count()
    total_pages = (total + per_page - 1) // per_page

    return jsonify({
        "success": True,
        "prds": prds,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages
        }
    })


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@app.route('/prd/<prd_id>/export/json')
def export_json(prd_id: str):
    """Export PRD as JSON file."""
    try:
        prd = prd_store.load(prd_id)
        import json
        response = Response(
            json.dumps(prd.to_ralph_format(), indent=2),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename=prd-{prd.project_name}.json'
            }
        )
        return response
    except Exception as e:
        flash(f'Failed to export: {e}', 'error')
        return redirect(url_for('view_prd', prd_id=prd_id))


@app.route('/prd/<prd_id>/export/markdown')
def export_markdown(prd_id: str):
    """Export PRD as Markdown file."""
    try:
        prd = prd_store.load(prd_id)
        rd = prd.to_ralph_format()

        md = f"# {rd['pn']}\n\n"
        md += f"**Description:** {rd['pd']}\n\n"
        md += f"## Starter Prompt\n\n{rd['sp']}\n\n"
        md += f"## Tech Stack\n\n"
        md += f"- Language: {rd['ts'].get('lang', 'N/A')}\n"
        md += f"- Framework: {rd['ts'].get('fw', 'N/A')}\n"
        md += f"- Database: {rd['ts'].get('db', 'N/A')}\n"
        if rd['ts'].get('oth'):
            md += f"- Other: {', '.join(rd['ts']['oth'])}\n"
        md += f"\n## File Structure\n\n"
        for f in rd['fs']:
            md += f"- `{f}`\n"
        md += f"\n## Tasks\n\n"

        for cat_id, cat in rd['p'].items():
            md += f"### {cat['n']} [{cat_id}]\n\n"
            for task in cat['t']:
                md += f"#### {task['id']} [{task['pr']}]\n\n"
                md += f"**{task['ti']}**\n\n"
                md += f"- Description: {task['d']}\n"
                md += f"- File: `{task['f']}`\n\n"

        response = Response(
            md,
            mimetype='text/markdown',
            headers={
                'Content-Disposition': f'attachment; filename=prd-{prd.project_name}.md'
            }
        )
        return response
    except Exception as e:
        flash(f'Failed to export: {e}', 'error')
        return redirect(url_for('view_prd', prd_id=prd_id))


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║              ███████╗██╗   ██╗██████╗ ████████╗                   ║
║              ██╔════╝██║   ██║██╔══██╗╚══██╔══╝                   ║
║              ███████╗██║   ██║██████╔╝   ██║                      ║
║              ╚════██║██║   ██║██╔══██╗   ██║                      ║
║              ███████║╚██████╔╝██████╔╝   ██║                      ║
║              ╚══════╝ ╚═════╝ ╚═════╝    ╚═╝                      ║
║                                                                   ║
║                    P R D   C R E A T O R                          ║
║                                                                   ║
║                   [Starting Flask Server...]                      ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    print(f"> Model: {OLLAMA_MODEL}")
    print(f"> Ollama URL: {OLLAMA_URL}")
    print(f"> Storage: {PRD_STORAGE_PATH}")
    print(f"> Debug: {DEBUG}")
    print()

    app.run(host='0.0.0.0', port=8000, debug=DEBUG)

# ============================================================================
# SESSION CLEANUP (Complete Ephemerality)
# ============================================================================

def cleanup_old_sessions():
    """Remove sessions older than 1 hour."""
    cutoff = datetime.utcnow() - timedelta(hours=1)
    to_delete = []

    for session_id, session in sessions.items():
        if session['created_at'] < cutoff:
            to_delete.append(session_id)

    for session_id in to_delete:
        del sessions[session_id]
        # Also cleanup from Ralph's sessions
        if session_id in ralph._sessions:
            del ralph._sessions[session_id]

    logger.info(f"Cleaned up {len(to_delete)} old sessions")

# Run cleanup every 30 minutes
import threading
def cleanup_worker():
    while True:
        try:
            cleanup_old_sessions()
            threading.Event().wait(1800)  # 30 minutes
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            threading.Event().wait(60)

cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
cleanup_thread.start()
