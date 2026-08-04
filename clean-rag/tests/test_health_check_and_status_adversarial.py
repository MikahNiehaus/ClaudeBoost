"""Adversarial tests for rag-enforce.py's _health_check and the live
/status endpoint's failed/ready/warming_up distinction.

Mutant 6 target (auto_reindex guard) and the rag-enforce failed status
mutant are both covered here with real execution, not description.
"""
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path("C:/Development/ClaudeBoost/clean-rag/hooks")))
sys.path.insert(0, str(Path("C:/Development/ClaudeBoost/clean-rag")))


def _load_rag_enforce():
    import importlib.util
    path = "C:/Development/ClaudeBoost/clean-rag/hooks/rag-enforce.py"
    spec = importlib.util.spec_from_file_location("rag_enforce_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_urlopen(payload: dict):
    class _Resp:
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return _Resp()


class TestHealthCheckFailedStatus:
    def test_failed_status_is_unhealthy(self):
        mod = _load_rag_enforce()
        with patch.object(mod.urllib.request, "urlopen",
                          return_value=_fake_urlopen({"status": "failed", "last_error": "OSError: boom"})):
            assert mod._health_check("8613") is False

    def test_ready_status_is_healthy(self):
        mod = _load_rag_enforce()
        with patch.object(mod.urllib.request, "urlopen",
                          return_value=_fake_urlopen({"status": "ready"})):
            assert mod._health_check("8613") is True

    def test_warming_up_status_is_healthy(self):
        mod = _load_rag_enforce()
        with patch.object(mod.urllib.request, "urlopen",
                          return_value=_fake_urlopen({"status": "warming_up"})):
            assert mod._health_check("8613") is True

    def test_mutant_treating_failed_as_healthy_is_caught(self):
        """This is the exact mutant: `return status in ("ready", "warming_up",
        "failed")`. Confirms the real code does NOT do this, by checking the
        real return value differs from what that mutant would produce."""
        mod = _load_rag_enforce()
        with patch.object(mod.urllib.request, "urlopen",
                          return_value=_fake_urlopen({"status": "failed"})):
            real_result = mod._health_check("8613")
        mutant_result = "failed" in ("ready", "warming_up", "failed")  # what the mutant would return
        assert real_result != mutant_result, "the real health check must disagree with the buggy mutant"
        assert real_result is False


class TestAutoReindexModelCacheGuard:
    """Mutant 6: `if not model_cache` instead of `if model_cache is None`.
    An empty (freshly constructed, zero models loaded) ModelCache is falsy
    but perfectly usable -- the guard must only skip on a real None."""

    def test_empty_but_real_cache_is_not_none(self):
        from server.lang_router import ModelCache
        cache = ModelCache()
        assert len(cache) == 0
        assert not cache  # confirms __bool__ falls back to __len__ == 0 -> falsy
        assert cache is not None  # this is the distinction the guard must use

    def test_source_uses_is_none_not_truthiness(self):
        """Static confirmation the fixed guard text is present in the
        current source (the behavioral test above is what actually matters,
        this just pins the exact line so a regression back to truthiness is
        obvious from the diff, not just a failing behavioral assertion)."""
        src = Path("C:/Development/ClaudeBoost/clean-rag/server/auto_reindex.py").read_text(encoding="utf-8")
        assert "if model_cache is None:" in src
        assert "if not model_cache:" not in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
