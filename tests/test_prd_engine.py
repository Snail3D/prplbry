"""
Unit tests for PRD Engine
TEST-001: Write unit tests for LLaMA model processing
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from prd_engine import PRDEngine, PRDCache
from exceptions import PRDGenerationError, ModelUnavailableError


class TestPRDCache:
    """Tests for PRD caching functionality."""

    def test_cache_hit(self):
        """Test retrieving cached PRD."""
        cache = PRDCache(ttl=3600)

        prompt = "Build a todo app"
        model = "llama3.2"
        task_count = 34
        prd = {"pn": "Todo App", "pd": "A todo application"}

        cache.set(prompt, model, task_count, prd)
        result = cache.get(prompt, model, task_count)

        assert result == prd

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = PRDCache(ttl=3600)

        result = cache.get("nonexistent", "llama3.2", 34)
        assert result is None

    def test_cache_expiration(self):
        """Test cache expires after TTL."""
        cache = PRDCache(ttl=0)  # Instant expiration

        prd = {"pn": "Test"}
        cache.set("prompt", "llama3.2", 34, prd)

        # Should be expired immediately
        result = cache.get("prompt", "llama3.2", 34)
        assert result is None

    def test_cache_clear(self):
        """Test clearing cache."""
        cache = PRDCache()
        cache.set("prompt", "llama3.2", 34, {"pn": "Test"})

        cache.clear()
        result = cache.get("prompt", "llama3.2", 34)

        assert result is None


class TestPRDEngine:
    """Tests for PRD generation engine."""

    @pytest.fixture
    def mock_ollama(self):
        """Mock Ollama client."""
        with patch('prd_engine.ollama') as mock:
            client = MagicMock()
            mock.Client.return_value = client
            client.list.return_value = {"models": [{"name": "llama3.2"}]}
            yield client

    @pytest.fixture
    def engine(self, mock_ollama):
        """Create a PRD engine instance."""
        return PRDEngine(model="llama3.2", enable_cache=False)

    def test_init_with_ollama(self, mock_ollama):
        """Test engine initialization with Ollama."""
        engine = PRDEngine(model="llama3.2")

        assert engine.model == "llama3.2"
        assert engine.ollama_client is not None

    def test_init_without_backends(self):
        """Test engine fails without any backend."""
        with patch('prd_engine.OLLAMA_AVAILABLE', False):
            with pytest.raises(ModelUnavailableError):
                PRDEngine(grok_api_key="", ollama_url="invalid://url")

    def test_build_prompt(self, engine):
        """Test prompt building."""
        prompt = engine._build_prompt(
            project_name="Todo App",
            description="A simple todo app",
            starter_prompt="I want a todo app",
            tech_stack={"lang": "Python", "fw": "Flask"},
            task_count=34
        )

        assert "Todo App" in prompt
        assert "A simple todo app" in prompt
        assert "34" in prompt
        assert "Python" in prompt

    def test_parse_valid_json_response(self, engine):
        """Test parsing valid JSON response."""
        json_response = '''{"pn": "Test", "pd": "Description", "sp": "Prompt", "ts": {}, "fs": [], "p": {}}'''

        result = engine._parse_response(json_response)

        assert result["pn"] == "Test"
        assert result["pd"] == "Description"

    def test_parse_markdown_json_response(self, engine):
        """Test parsing JSON from markdown code block."""
        md_response = '''```json
{"pn": "Test", "pd": "Description", "sp": "Prompt", "ts": {}, "fs": [], "p": {}}
```'''

        result = engine._parse_response(md_response)

        assert result["pn"] == "Test"

    def test_parse_invalid_json_raises_error(self, engine):
        """Test parsing invalid JSON raises error."""
        with pytest.raises(PRDGenerationError):
            engine._parse_response("not valid json")

    def test_validate_prd_structure_valid(self, engine):
        """Test validating correct PRD structure."""
        prd = {
            "pn": "Test",
            "pd": "Description",
            "sp": "Prompt",
            "ts": {},
            "fs": [],
            "p": {
                "00_security": {"n": "Security", "t": []},
                "01_setup": {"n": "Setup", "t": []},
                "02_core": {"n": "Core", "t": []},
                "03_api": {"n": "API", "t": []},
                "04_test": {"n": "Testing", "t": []}
            }
        }

        # Should not raise
        engine._validate_prd_structure(prd)

    def test_validate_prd_structure_missing_fields(self, engine):
        """Test validating PRD with missing fields raises error."""
        prd = {"pn": "Test"}

        with pytest.raises(PRDGenerationError):
            engine._validate_prd_structure(prd)

    def test_generate_prd_with_ollama(self, engine, mock_ollama):
        """Test generating PRD with Ollama."""
        mock_response = {
            "message": {
                "content": '{"pn": "Todo App", "pd": "Description", "sp": "Prompt", "ts": {}, "fs": [], "p": {}}'
            }
        }
        mock_ollama.chat.return_value = mock_response

        result = engine.generate_prd(
            project_name="Todo App",
            description="A todo app",
            starter_prompt="Build a todo app",
            tech_stack={},
            task_count=10
        )

        assert result["pn"] == "Todo App"
        mock_ollama.chat.assert_called_once()

    def test_generate_prd_with_grok_fallback(self):
        """Test Grok API fallback when Ollama fails."""
        with patch('prd_engine.OLLAMA_AVAILABLE', False):
            engine = PRDEngine(grok_api_key="test-key", ollama_url="invalid://")

            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{
                        "message": {
                            "content": '{"pn": "Test", "pd": "Desc", "sp": "Prompt", "ts": {}, "fs": [], "p": {}}'
                        }
                    }]
                }
                mock_post.return_value = mock_response

                result = engine.generate_prd(
                    project_name="Test",
                    description="Desc",
                    starter_prompt="Prompt",
                    tech_stack={},
                    task_count=10
                )

                assert result["pn"] == "Test"

    def test_cache_used_on_repeated_request(self):
        """Test that cache is used for identical requests."""
        with patch('prd_engine.ollama') as mock_ollama:
            client = MagicMock()
            mock_ollama.Client.return_value = client
            client.list.return_value = {"models": [{"name": "llama3.2"}]}
            client.chat.return_value = {
                "message": {"content": '{"pn": "Test", "pd": "Desc", "sp": "Prompt", "ts": {}, "fs": [], "p": {}'}'}

            engine = PRDEngine(model="llama3.2", enable_cache=True)

            # First call
            engine.generate_prd("Test", "Desc", "Prompt", {}, 10)

            # Second call - should use cache
            engine.generate_prd("Test", "Desc", "Prompt", {}, 10)

            # Should only call Ollama once (first call cached)
            assert client.chat.call_count == 1
