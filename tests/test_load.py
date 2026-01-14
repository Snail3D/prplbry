"""
Load tests for PRD Creator
X-1010: Implement load testing
"""
import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import app
from prd_store import PRDStore, PRD
from prd_engine import PRDCache


@pytest.mark.skip(reason="Load tests - run manually with pytest -v tests/test_load.py")
class TestLoad:
    """Load tests for PRD Creator."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance."""
        return PRDCache(ttl=3600)

    def test_cache_concurrent_access(self, cache):
        """Test cache handles concurrent access."""
        def write_to_cache(i):
            cache.set(f"prompt_{i}", "llama3.2", 34, {"pn": f"PRD {i}"})
            return True

        def read_from_cache(i):
            return cache.get(f"prompt_{i}", "llama3.2", 34)

        # Concurrent writes
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_to_cache, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]

        assert all(results)

        # Concurrent reads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_from_cache, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]

        # All reads should return cached values
        assert all(r is not None for r in results)

    def test_prd_store_concurrent_writes(self):
        """Test PRD store handles concurrent writes."""
        temp_dir = "/tmp/test_prd_store_concurrent"
        import shutil
        import os
        from pathlib import Path

        # Cleanup if exists
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)

        store = PRDStore(storage_path=Path(temp_dir))

        def create_prd(i):
            prd = PRD(
                project_name=f"Concurrent Test {i}",
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
            return store.save(prd)

        # Concurrent PRD creation
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_prd, i) for i in range(50)]
            prd_ids = [f.result() for f in as_completed(futures)]

        # All PRDs should be created successfully
        assert len(prd_ids) == 50
        assert len(set(prd_ids)) == 50  # All unique IDs

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_api_concurrent_requests(self):
        """Test API handles concurrent requests."""
        app.config['TESTING'] = True

        def make_request(client):
            response = client.get('/api/status')
            return response.status_code == 200

        with app.test_client() as client:
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(make_request, client) for _ in range(100)]
                results = [f.result() for f in as_completed(futures)]

        # All requests should succeed
        assert all(results)

    def test_rate_limiting_under_load(self):
        """Test rate limiting holds up under load."""
        app.config['TESTING'] = True

        def make_generation_request(client, i):
            response = client.post('/api/prd/generate',
                                  json={
                                      "project_name": f"Load Test {i}",
                                      "description": "Test",
                                      "starter_prompt": "Test",
                                      "task_count": 5,
                                      "tech_stack": "python-flask"
                                  },
                                  content_type='application/json')
            return response.status_code

        with app.test_client() as client:
            # Make 50 requests concurrently
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(make_generation_request, client, i) for i in range(50)]
                status_codes = [f.result() for f in as_completed(futures)]

        # Some should be rate limited (429)
        # Others should be 400 (validation) or 200 (success - if mock available)
        assert any(code == 429 for code in status_codes), "Expected some requests to be rate limited"

    def test_cache_performance(self, cache):
        """Test cache performance with many entries."""
        import time

        # Write 1000 entries
        start = time.time()
        for i in range(1000):
            cache.set(f"prompt_{i}", "llama3.2", 34, {"pn": f"PRD {i}"})
        write_time = time.time() - start

        print(f"\nWrote 1000 cache entries in {write_time:.3f}s")

        # Read 1000 entries
        start = time.time()
        for i in range(1000):
            cache.get(f"prompt_{i}", "llama3.2", 34)
        read_time = time.time() - start

        print(f"Read 1000 cache entries in {read_time:.3f}s")

        # Performance should be reasonable
        assert write_time < 1.0, "Cache write performance too slow"
        assert read_time < 0.5, "Cache read performance too slow"

    def test_memory_usage_under_load(self):
        """Test memory usage doesn't grow excessively."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create and cache many PRDs
        cache = PRDCache()
        for i in range(1000):
            cache.set(f"prompt_{i}", "llama3.2", 34, {
                "pn": f"PRD {i}",
                "pd": "Description",
                "sp": "Starter prompt",
                "ts": {},
                "fs": [],
                "p": {}
            })

        final_memory = process.memory_info().rss
        memory_growth = final_memory - initial_memory

        print(f"\nMemory growth: {memory_growth / 1024 / 1024:.2f} MB")

        # Memory growth should be reasonable (< 100 MB for 1000 cached PRDs)
        assert memory_growth < 100 * 1024 * 1024, "Memory usage grew too much"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
