"""
Integration tests for PRD Creator
X-951: Implement integration testing
"""
import pytest
import json
import tempfile
import shutil
from pathlib import Path

from app import app
from prd_store import PRDStore, PRD


@pytest.fixture
def client():
    """Create a test client."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'

    # Use temp directory for storage
    temp_dir = tempfile.mkdtemp()
    app.config['prd_storage'] = temp_dir

    with app.test_client() as client:
        yield client

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_prd_data():
    """Sample PRD data for testing."""
    return {
        "project_name": "Test Project",
        "description": "A test project",
        "starter_prompt": "Build a test project",
        "model": "llama3.2",
        "task_count": 10,
        "tech_stack": "python-flask"
    }


class TestRoutes:
    """Tests for Flask routes."""

    def test_index_route(self, client):
        """Test index page loads."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'PRD CREATOR' in response.data

    def test_create_prd_route(self, client):
        """Test create PRD page loads."""
        response = client.get('/create')
        assert response.status_code == 200
        assert b'CREATE NEW PRD' in response.data

    def test_list_prds_route(self, client):
        """Test list PRDs page loads."""
        response = client.get('/prds')
        assert response.status_code == 200


class TestAPIEndpoints:
    """Tests for API endpoints."""

    def test_api_status(self, client):
        """Test status endpoint."""
        response = client.get('/api/status')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'status' in data
        assert data['status'] == 'online'

    def test_api_generate_prd_missing_fields(self, client):
        """Test PRD generation with missing fields."""
        response = client.post('/api/prd/generate',
                              json={"project_name": "Test"},
                              content_type='application/json')
        assert response.status_code == 400

    def test_api_generate_prd_invalid_project_name(self, client):
        """Test PRD generation with invalid project name."""
        response = client.post('/api/prd/generate',
                              json={
                                  "project_name": "Test<script>",
                                  "description": "A test project",
                                  "starter_prompt": "Build a test",
                                  "task_count": 10,
                                  "tech_stack": "python-flask"
                              },
                              content_type='application/json')
        assert response.status_code == 400

    def test_api_generate_prd_invalid_task_count(self, client):
        """Test PRD generation with invalid task count."""
        response = client.post('/api/prd/generate',
                              json={
                                  "project_name": "Test",
                                  "description": "A test project",
                                  "starter_prompt": "Build a test",
                                  "task_count": 200,  # Too high
                                  "tech_stack": "python-flask"
                              },
                              content_type='application/json')
        assert response.status_code == 400

    def test_api_get_nonexistent_prd(self, client):
        """Test getting non-existent PRD."""
        response = client.get('/api/prd/nonexistent-id')
        assert response.status_code == 404

    def test_api_list_prds(self, client):
        """Test listing PRDs."""
        response = client.get('/api/prds')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'success' in data
        assert 'prds' in data
        assert 'pagination' in data

    def test_api_list_prds_pagination(self, client):
        """Test PRD list pagination."""
        response = client.get('/api/prds?page=1&per_page=10')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['pagination']['page'] == 1
        assert data['pagination']['per_page'] == 10

    def test_rate_limiting(self, client):
        """Test rate limiting is enforced."""
        # Make many requests quickly
        responses = []
        for _ in range(15):  # Exceed limit of 10 per minute
            response = client.post('/api/prd/generate',
                                  json={
                                      "project_name": f"Test{_}",
                                      "description": "Test",
                                      "starter_prompt": "Test",
                                      "task_count": 5,
                                      "tech_stack": "python-flask"
                                  },
                                  content_type='application/json')
            responses.append(response)

        # At least one should be rate limited
        rate_limited = any(r.status_code == 429 for r in responses)
        assert rate_limited, "Expected rate limiting to trigger"


class TestPRDStore:
    """Tests for PRD storage."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary PRD store."""
        temp_dir = tempfile.mkdtemp()
        store = PRDStore(storage_path=Path(temp_dir))

        yield store

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_save_and_load_prd(self, temp_store):
        """Test saving and loading a PRD."""
        prd = PRD(
            project_name="Test Project",
            project_description="A test project",
            starter_prompt="Build a test project",
            tech_stack={"lang": "Python", "fw": "Flask"},
            file_structure=["app.py", "config.py"],
            prds={
                "00_security": {"n": "Security", "t": []},
                "01_setup": {"n": "Setup", "t": []},
                "02_core": {"n": "Core", "t": []},
                "03_api": {"n": "API", "t": []},
                "04_test": {"n": "Testing", "t": []}
            }
        )

        prd_id = temp_store.save(prd)
        loaded_prd = temp_store.load(prd_id)

        assert loaded_prd.project_name == "Test Project"
        assert loaded_prd.id == prd_id

    def test_delete_prd(self, temp_store):
        """Test deleting a PRD."""
        prd = PRD(
            project_name="Test",
            project_description="Test",
            starter_prompt="Test",
            tech_stack={},
            file_structure=[],
            prds={
                "00_security": {"n": "Security", "t": []},
                "01_setup": {"n": "Setup", "t": []},
                "02_core": {"n": "Core", "t": []},
                "03_api": {"n": "API", "t": []},
                "04_test": {"n": "Testing", "t": []}
            }
        )

        prd_id = temp_store.save(prd)
        assert temp_store.delete(prd_id) == True

        # Should be deleted
        with pytest.raises(Exception):
            temp_store.load(prd_id)

    def test_list_prds(self, temp_store):
        """Test listing PRDs."""
        # Create multiple PRDs
        for i in range(5):
            prd = PRD(
                project_name=f"Test Project {i}",
                project_description="Test",
                starter_prompt="Test",
                tech_stack={},
                file_structure=[],
                prds={
                    "00_security": {"n": "Security", "t": []},
                    "01_setup": {"n": "Setup", "t": []},
                    "02_core": {"n": "Core", "t": []},
                    "03_api": {"n": "API", "t": []},
                    "04_test": {"n": "Testing", "t": []}
                }
            )
            temp_store.save(prd)

        prds = temp_store.list_all()
        assert len(prds) == 5

    def test_prd_validation(self, temp_store):
        """Test PRD validation."""
        # Invalid PRD (missing fields)
        prd = PRD(
            project_name="",  # Empty name should fail
            project_description="Test",
            starter_prompt="Test",
            tech_stack={},
            file_structure=[],
            prds={}
        )

        with pytest.raises(Exception):  # ValidationError
            temp_store.save(prd)


class TestInputValidation:
    """Tests for input validation (X-910/X-1000)."""

    def test_sql_injection_detection(self, client):
        """Test SQL injection patterns are detected."""
        response = client.post('/api/prd/generate',
                              json={
                                  "project_name": "Test'; DROP TABLE--",
                                  "description": "Test",
                                  "starter_prompt": "Test",
                                  "task_count": 10,
                                  "tech_stack": "python-flask"
                              },
                              content_type='application/json')

        # Should be rejected
        assert response.status_code == 400

    def test_xss_detection(self, client):
        """Test XSS patterns are detected."""
        response = client.post('/api/prd/generate',
                              json={
                                  "project_name": "<script>alert('xss')</script>",
                                  "description": "Test",
                                  "starter_prompt": "Test",
                                  "task_count": 10,
                                  "tech_stack": "python-flask"
                              },
                              content_type='application/json')

        # Should be rejected
        assert response.status_code == 400
