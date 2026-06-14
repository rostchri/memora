"""Tests fuer getrennten Embedding- und LLM-Provider.

Prueft:
- MEMORA_EMBEDDING_BASE_URL uebersteuert OPENAI_BASE_URL fuer den Embedding-Client
- Fallback auf OPENAI_* wenn MEMORA_EMBEDDING_*-Vars fehlen
- Dasselbe fuer LLM-Client (MEMORA_LLM_BASE_URL vs. OPENAI_BASE_URL)
- Kein Verhaltenswechsel wenn nur OPENAI_* gesetzt sind (Rueckwaertskompatibilitaet)
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_openai_stub(captured: Dict[str, Any]):
    """Erzeugt ein openai-Stub-Modul, das Client-kwargs in `captured` speichert."""
    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_openai = SimpleNamespace(OpenAI=FakeClient)
    return fake_openai


# ---------------------------------------------------------------------------
# embeddings.py — Embedding-Provider-Separation
# ---------------------------------------------------------------------------

class TestEmbeddingProviderSeparation:
    """MEMORA_EMBEDDING_* steuert den Embedding-Client."""

    def _call_with_env(self, monkeypatch, env: Dict[str, str]) -> Dict[str, Any]:
        """Ruft _compute_embedding_openai mit isoliertem Cache + gemocktem openai auf."""
        import memora.embeddings as emb_mod

        # Cache leeren damit Client neu gebaut wird
        monkeypatch.setattr(emb_mod, "_embedding_model_cache", {})

        # Alle relevanten Env-Vars setzen / loeschen
        for var in (
            "MEMORA_EMBEDDING_API_KEY", "MEMORA_EMBEDDING_BASE_URL",
            "MEMORA_EMBEDDING_MODEL",
            "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_EMBEDDING_MODEL",
        ):
            monkeypatch.delenv(var, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        captured: Dict[str, Any] = {}
        fake_openai = _make_openai_stub(captured)

        # openai.OpenAI(...).embeddings.create(...) → minimaler Stub
        fake_client = fake_openai.OpenAI
        orig_init = fake_client.__init__

        class FakeClientWithEmbeddings:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            @property
            def embeddings(self):
                create_mock = MagicMock()
                create_mock.create.return_value = SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.1, 0.2])]
                )
                return create_mock

        fake_openai.OpenAI = FakeClientWithEmbeddings

        with patch.dict("sys.modules", {"openai": fake_openai}):
            emb_mod._embedding_model_cache.clear()
            # Neu-importieren damit der Cache-State stimmt
            result = emb_mod._compute_embedding_openai("test text")

        return captured

    def test_memora_embedding_base_url_overrides_openai(self, monkeypatch):
        """MEMORA_EMBEDDING_BASE_URL hat Vorrang vor OPENAI_BASE_URL."""
        captured = self._call_with_env(monkeypatch, {
            "MEMORA_EMBEDDING_API_KEY": "memora-key",
            "MEMORA_EMBEDDING_BASE_URL": "http://nanogpt:8080/v1",
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_BASE_URL": "http://openai.example.com/v1",
        })
        assert captured["api_key"] == "memora-key"
        assert captured["base_url"] == "http://nanogpt:8080/v1"

    def test_fallback_to_openai_vars_when_memora_absent(self, monkeypatch):
        """Wenn MEMORA_EMBEDDING_* fehlen, werden OPENAI_* verwendet."""
        captured = self._call_with_env(monkeypatch, {
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_BASE_URL": "http://openai.example.com/v1",
        })
        assert captured["api_key"] == "openai-key"
        assert captured["base_url"] == "http://openai.example.com/v1"

    def test_memora_embedding_api_key_only(self, monkeypatch):
        """Nur MEMORA_EMBEDDING_API_KEY, kein base_url → kein base_url im Client."""
        captured = self._call_with_env(monkeypatch, {
            "MEMORA_EMBEDDING_API_KEY": "memora-only-key",
        })
        assert captured["api_key"] == "memora-only-key"
        assert "base_url" not in captured

    def test_no_api_key_falls_back_to_tfidf(self, monkeypatch):
        """Ohne API-Key → TF-IDF Fallback, kein Exception."""
        import memora.embeddings as emb_mod
        monkeypatch.setattr(emb_mod, "_embedding_model_cache", {})
        for var in (
            "MEMORA_EMBEDDING_API_KEY", "OPENAI_API_KEY",
            "MEMORA_EMBEDDING_BASE_URL", "OPENAI_BASE_URL",
        ):
            monkeypatch.delenv(var, raising=False)

        fake_openai = SimpleNamespace(OpenAI=MagicMock())
        with patch.dict("sys.modules", {"openai": fake_openai}):
            result = emb_mod._compute_embedding_openai("test text")

        # Muss ein nicht-leeres TF-IDF-Dict zurueckgeben
        assert isinstance(result, dict)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# storage.py — LLM-Provider-Separation
# ---------------------------------------------------------------------------

class TestLLMProviderSeparation:
    """MEMORA_LLM_* steuert den Dedup/Chat-LLM-Client."""

    def _build_client(self, monkeypatch, env: Dict[str, str]) -> Dict[str, Any]:
        """Ruft _get_llm_client mit isoliertem Cache + gemocktem openai auf."""
        import memora.storage as storage_mod

        # Cache leeren
        monkeypatch.setattr(storage_mod, "_llm_client_cache", {})
        monkeypatch.setattr(storage_mod, "LLM_ENABLED", True)

        for var in (
            "MEMORA_LLM_API_KEY", "MEMORA_LLM_BASE_URL",
            "OPENAI_API_KEY", "OPENAI_BASE_URL",
        ):
            monkeypatch.delenv(var, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        captured: Dict[str, Any] = {}

        class FakeLLMClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        fake_openai = SimpleNamespace(OpenAI=FakeLLMClient)
        with patch.dict("sys.modules", {"openai": fake_openai}):
            storage_mod._llm_client_cache.clear()
            client = storage_mod._get_llm_client()

        return captured

    def test_memora_llm_base_url_overrides_openai(self, monkeypatch):
        """MEMORA_LLM_BASE_URL hat Vorrang vor OPENAI_BASE_URL."""
        captured = self._build_client(monkeypatch, {
            "MEMORA_LLM_API_KEY": "llm-key",
            "MEMORA_LLM_BASE_URL": "http://openrouter.ai/api/v1",
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_BASE_URL": "http://openai.example.com/v1",
        })
        assert captured["api_key"] == "llm-key"
        assert captured["base_url"] == "http://openrouter.ai/api/v1"

    def test_fallback_to_openai_vars_when_memora_llm_absent(self, monkeypatch):
        """Wenn MEMORA_LLM_* fehlen, werden OPENAI_* verwendet (Rueckwaertskompatibilitaet)."""
        captured = self._build_client(monkeypatch, {
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_BASE_URL": "http://openai.example.com/v1",
        })
        assert captured["api_key"] == "openai-key"
        assert captured["base_url"] == "http://openai.example.com/v1"

    def test_no_api_key_returns_none(self, monkeypatch):
        """Ohne API-Key liefert _get_llm_client() None."""
        import memora.storage as storage_mod
        monkeypatch.setattr(storage_mod, "_llm_client_cache", {})
        monkeypatch.setattr(storage_mod, "LLM_ENABLED", True)
        for var in ("MEMORA_LLM_API_KEY", "OPENAI_API_KEY",
                    "MEMORA_LLM_BASE_URL", "OPENAI_BASE_URL"):
            monkeypatch.delenv(var, raising=False)

        fake_openai = SimpleNamespace(OpenAI=MagicMock())
        with patch.dict("sys.modules", {"openai": fake_openai}):
            storage_mod._llm_client_cache.clear()
            client = storage_mod._get_llm_client()

        assert client is None

    def test_only_openai_api_key_no_base_url(self, monkeypatch):
        """Nur OPENAI_API_KEY (kein base_url) → kein base_url im Client."""
        captured = self._build_client(monkeypatch, {
            "OPENAI_API_KEY": "only-key",
        })
        assert captured["api_key"] == "only-key"
        assert "base_url" not in captured
