"""Tests for app/model_client.py and the /chat endpoints.

Every test here uses a mocked/fake client or FastAPI's TestClient — NO real
network call, NO running Ollama dependency, NO hosted API spend.  A test that
hit a real backend would be non-deterministic (model output varies), slow,
flaky offline, and expensive against a paid API — the mock replaces all of
that with a known, fixed response so the test checks OUR logic.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.model_client import ask_model

client = TestClient(app)


# ---------------------------------------------------------------------------
# Unit tests for ask_model — the shared function (lesson 9, both paths)
# ---------------------------------------------------------------------------

class TestAskModelHappyPath:
    def test_returns_reply_text(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="a real-looking reply"))
        ]

        result = ask_model(fake_client, model="test-model", message="hello")

        assert result == "a real-looking reply"

    def test_builds_the_correct_request(self):
        """Adversarial: does ask_model pass the right model + message through?

        A bug that silently sent the wrong model name or dropped the message
        would still return a "reply", so the happy-path content test alone
        cannot catch it.  Assert the exact call that reached the client.
        """
        latest_message = {"role": "user", "content": "the-message"}
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="x"))
        ]

        ask_model(fake_client, model="my-model", message="the-message")

        fake_client.chat.completions.create.assert_called_once_with(
            model="my-model",
            messages=[latest_message],
            max_tokens=500,
        )


class TestAskModelErrorPath:
    def test_propagates_a_real_client_error(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = ConnectionError(
            "local server not running"
        )

        try:
            ask_model(fake_client, model="test-model", message="hello")
            assert False, "expected ConnectionError to propagate"
        except ConnectionError:
            pass

    def test_does_not_swallow_or_rewrap_error(self):
        """Adversarial: errors must reach the caller untouched, not be hidden.

        The wrapper must never catch-and-return a placeholder on failure — a
        silent fallback would make every error look like success.  Assert the
        exception type survives unwrapped through ask_model.
        """
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError) as excinfo:
            ask_model(fake_client, model="m", message="x")

        assert str(excinfo.value) == "boom"


# ---------------------------------------------------------------------------
# Endpoint tests — full HTTP contract through TestClient (no real backend)
# ---------------------------------------------------------------------------

class TestChatLocalEndpoint:
    def test_returns_chat_response_shape_with_mocked_client(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="local reply"))
        ]

        with patch("app.main.get_client", return_value=fake_client):
            resp = client.post("/chat/local", json={"message": "hi"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "local reply"
        assert body["backend"] == "ollama"
        assert body["model"] == "llama3.2:3b"

    def test_rejects_missing_message_field(self):
        resp = client.post("/chat/local", json={})
        assert resp.status_code == 422  # Pydantic validation


class TestChatHostedEndpoint:
    def test_returns_chat_response_shape_with_mocked_client(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="hosted reply"))
        ]

        with patch("app.main.get_client", return_value=fake_client):
            resp = client.post("/chat/hosted", json={"message": "hi"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "hosted reply"
        assert body["backend"] == "hosted"

    def test_returns_502_when_backend_fails(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = ConnectionError(
            "provider down"
        )

        with patch("app.main.get_client", return_value=fake_client):
            resp = client.post("/chat/hosted", json={"message": "hi"})

        assert resp.status_code == 502  # surfaced as a clean HTTP error


# ---------------------------------------------------------------------------
# /chat/auto + /health — auto-routing bonus (probe mocked, no real network)
# ---------------------------------------------------------------------------

class TestChatAutoEndpoint:
    def test_routes_to_ollama_when_local_is_up(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="auto local reply"))
        ]

        with patch("app.main.server_up", return_value=True), patch(
            "app.main.get_client", return_value=fake_client
        ):
            resp = client.post("/chat/auto", json={"message": "hi"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["backend"] == "ollama"
        assert body["reply"] == "auto local reply"

    def test_falls_back_to_hosted_when_local_is_down(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="auto hosted reply"))
        ]

        with patch("app.main.server_up", return_value=False), patch(
            "app.main.get_client", return_value=fake_client
        ):
            resp = client.post("/chat/auto", json={"message": "hi"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["backend"] == "hosted"
        assert body["reply"] == "auto hosted reply"

    def test_probe_is_free_and_probes_local_only(self):
        """Adversarial: /chat/auto must NOT send a real model request to probe —
        when the local path wins, only the local client is ever created.
        """
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="x"))
        ]

        with patch("app.main.server_up", return_value=True), patch(
            "app.main.get_client", return_value=fake_client
        ) as mock_get_client:
            client.post("/chat/auto", json={"message": "hi"})

        assert mock_get_client.call_count == 1
        assert mock_get_client.call_args.kwargs["use_local"] is True


class TestHealthEndpoint:
    def test_reports_both_backends_with_mocked_probe(self):
        with patch("app.main.server_up", side_effect=[True, True]):
            resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["ollama"] is True
        assert body["hosted"] is True
        assert body["auto_backend"] == "ollama"

    def test_reports_hosted_fallback_when_ollama_down(self):
        with patch("app.main.server_up", side_effect=[False, True]):
            resp = client.get("/health")

        body = resp.json()
        assert body["ollama"] is False
        assert body["hosted"] is True
        assert body["auto_backend"] == "hosted"