"""
PRD Generation Engine
SEC-003: Initialize LLaMA model
CORE-001: Implement LLaMA model processing
X-931/X-1005: Implement caching
"""
import json
import hashlib
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

import requests

from config import (
    OLLAMA_URL, OLLAMA_MODEL,
    PRD_GENERATION_PROMPT, CACHE_DEFAULT_TIMEOUT
)
from exceptions import PRDGenerationError, ModelUnavailableError

logger = logging.getLogger(__name__)


class PRDCache:
    """Simple in-memory cache for generated PRDs."""

    def __init__(self, ttl: int = CACHE_DEFAULT_TIMEOUT):
        self._cache: Dict[str, tuple] = {}
        self._ttl = ttl

    def _generate_key(self, prompt: str, model: str, task_count: int) -> str:
        """Generate cache key from prompt parameters."""
        key_data = f"{prompt}:{model}:{task_count}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, prompt: str, model: str, task_count: int) -> Optional[Dict[str, Any]]:
        """Get cached PRD if available and not expired."""
        key = self._generate_key(prompt, model, task_count)
        if key in self._cache:
            prd, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                logger.info(f"Cache hit for key: {key[:16]}...")
                return prd
            else:
                # Expired, remove from cache
                del self._cache[key]
        return None

    def set(self, prompt: str, model: str, task_count: int, prd: Dict[str, Any]) -> None:
        """Cache a generated PRD."""
        key = self._generate_key(prompt, model, task_count)
        self._cache[key] = (prd, time.time())
        logger.info(f"Cached PRD with key: {key[:16]}...")

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()


class PRDEngine:
    """
    PRD Generation Engine using LLaMA (via Ollama).

    Supports:
    - Local LLaMA models via Ollama
    - Response caching
    - Retry with exponential backoff
    """

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        ollama_url: str = OLLAMA_URL,
        enable_cache: bool = True
    ):
        """
        Initialize the PRD engine.

        Args:
            model: Model name (llama3.2, etc.)
            ollama_url: URL for Ollama API
            enable_cache: Enable response caching
        """
        self.model = model
        self.ollama_url = ollama_url
        self.enable_cache = enable_cache

        # Initialize cache
        self.cache = PRDCache() if enable_cache else None

        # Initialize Ollama client
        self.ollama_client = None
        if OLLAMA_AVAILABLE:
            try:
                self.ollama_client = ollama.Client(base_url=ollama_url)
                self._validate_ollama()
            except Exception as e:
                logger.warning(f"Ollama initialization failed: {e}")
                self.ollama_client = None

        # Validate Ollama is available
        if not self.ollama_client:
            raise ModelUnavailableError(
                self.model,
                reason="Ollama is not available. Please install and run Ollama."
            )

        logger.info(f"PRD Engine initialized with model: {model}")

    def _validate_ollama(self) -> None:
        """Check if Ollama is accessible and model is available."""
        try:
            models = self.ollama_client.list()
            model_names = [m.get("name", "").split(":")[0] for m in models.get("models", [])]

            if self.model not in model_names:
                logger.warning(
                    f"Model '{self.model}' not found in Ollama. "
                    f"Available: {', '.join(model_names)}"
                )
                logger.info(f"Pull model with: ollama pull {self.model}")
        except Exception as e:
            raise ModelUnavailableError(self.model, reason=f"Ollama check failed: {e}")

    def generate_prd(
        self,
        project_name: str,
        description: str,
        starter_prompt: str,
        tech_stack: Dict[str, str],
        task_count: int = 34
    ) -> Dict[str, Any]:
        """
        Generate a complete Ralph Mode PRD.

        Args:
            project_name: Name of the project
            description: Project description
            starter_prompt: Initial idea/prompt
            tech_stack: Technology stack dict (lang, fw, db, oth)
            task_count: Number of tasks to generate

        Returns:
            Complete PRD dictionary

        Raises:
            PRDGenerationError: If generation fails
        """
        # Check cache first
        if self.cache:
            cached = self.cache.get(starter_prompt, self.model, task_count)
            if cached:
                return cached

        # Build the prompt
        prompt = self._build_prompt(
            project_name, description, starter_prompt, tech_stack, task_count
        )

        # Try to generate with retry
        prd = self._generate_with_retry(prompt)

        # Cache the result
        if self.cache:
            self.cache.set(starter_prompt, self.model, task_count, prd)

        return prd

    def _build_prompt(
        self,
        project_name: str,
        description: str,
        starter_prompt: str,
        tech_stack: Dict[str, str],
        task_count: int
    ) -> str:
        """Build the PRD generation prompt."""
        tech_stack_str = ", ".join([
            f"{k}: {v}" for k, v in tech_stack.items() if v
        ])

        return PRD_GENERATION_PROMPT.format(
            project_name=project_name,
            description=description,
            starter_prompt=starter_prompt,
            tech_stack=tech_stack_str,
            task_count=task_count
        )

    def _generate_with_retry(self, prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Generate PRD with exponential backoff retry.
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}: Generating with Ollama ({self.model})")
                return self._generate_ollama(prompt)
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(f"Ollama attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)

        # All attempts failed
        raise PRDGenerationError(
            f"Failed to generate PRD after {max_retries} attempts",
            model=self.model,
            details={"last_error": str(last_error)}
        )

    def _generate_ollama(self, prompt: str) -> Dict[str, Any]:
        """Generate PRD using Ollama (local LLaMA)."""
        try:
            response = self.ollama_client.chat(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                options={
                    "temperature": 0.7,
                    "num_predict": 4096,
                }
            )

            content = response.get("message", {}).get("content", "")
            return self._parse_response(content)

        except Exception as e:
            raise PRDGenerationError(
                f"Ollama generation failed: {e}",
                model=self.model
            )

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """
        Parse LLM response into PRD structure.

        Handles JSON extraction from markdown code blocks.
        """
        # Try to extract JSON from markdown code block
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()

        # Parse JSON
        try:
            prd = json.loads(content)
            self._validate_prd_structure(prd)
            return prd
        except json.JSONDecodeError as e:
            raise PRDGenerationError(
                f"Failed to parse LLM response as JSON: {e}",
                details={"raw_response": content[:500]}
            )

    def _validate_prd_structure(self, prd: Dict[str, Any]) -> None:
        """Validate that the PRD has required fields."""
        required_fields = ["pn", "pd", "sp", "ts", "fs", "p"]
        missing = [f for f in required_fields if f not in prd]

        if missing:
            raise PRDGenerationError(
                f"Generated PRD missing required fields: {', '.join(missing)}",
                details={"prd": prd}
            )

        # Validate tasks structure
        if not isinstance(prd.get("p"), dict):
            raise PRDGenerationError(
                "PRD 'p' field must be a dict",
                details={"p_type": type(prd.get("p"))}
            )


# Singleton instance
_engine: Optional[PRDEngine] = None


def get_prd_engine() -> PRDEngine:
    """Get or create the PRD engine singleton."""
    global _engine
    if _engine is None:
        _engine = PRDEngine()
    return _engine


def reset_engine() -> None:
    """Reset the engine singleton (useful for testing)."""
    global _engine
    _engine = None
