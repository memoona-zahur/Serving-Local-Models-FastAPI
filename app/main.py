"""FastAPI service that wraps a local or hosted model behind one HTTP contract.

Endpoints, all sharing ONE model-calling function:

    POST /chat/local   -> Ollama on this machine (forced)
    POST /chat/hosted  -> hosted provider from .env (forced)
    POST /chat/auto    -> SERVICE picks backend: Ollama if reachable, else hosted
    GET  /health       -> free reachability probe (GET /models, no token spend)

Full-interaction endpoints build the same Pydantic request/response shape and
all call the SAME ``ask_model`` function; only the client and model name differ.
That symmetry is the whole point of today's build (see app/model_client.py).
"""

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.model_client import ask_model, get_client, server_up

app = FastAPI(
    title="Local & Hosted LLM API",
    description=(
        "Wraps an Ollama model and a hosted OpenAI-compatible model behind "
        "one shared request/response contract."
    ),
    version="1.0.0",
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    model: str
    reply: str
    backend: str


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    hosted: bool
    auto_backend: str


@app.get("/")
def root() -> dict:
    return {
        "service": "local-and-hosted-llm-api",
        "endpoints": ["/chat/local", "/chat/hosted", "/chat/auto"],
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report reachability of both backends (no token spend; GET /models probe only)."""
    local = server_up(
        os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1"),
        os.getenv("LOCAL_API_KEY", "ollama"),
    )
    hosted = server_up(
        os.getenv("HOSTED_BASE_URL", "https://api.openai.com/v1"),
        os.getenv("HOSTED_API_KEY", os.getenv("OPENAI_API_KEY", "")),
    )
    return HealthResponse(
        status="ok",
        ollama=local,
        hosted=hosted,
        auto_backend="ollama" if local else "hosted",
    )


@app.post("/chat/local", response_model=ChatResponse)
def chat_local(payload: ChatRequest) -> ChatResponse:
    """Ask the local Ollama model (llama3.2:3b by default)."""
    model = os.getenv("LOCAL_MODEL", "llama3.2:3b")
    try:
        return ChatResponse(
            model=model,
            reply=ask_model(get_client(use_local=True), model, payload.message),
            backend="ollama",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/chat/hosted", response_model=ChatResponse)
def chat_hosted(payload: ChatRequest) -> ChatResponse:
    """Ask the hosted model (Groq free tier by default, per .env)."""
    model = os.getenv("HOSTED_MODEL", "qwen/qwen3.8-27b")
    try:
        return ChatResponse(
            model=model,
            reply=ask_model(get_client(use_local=False), model, payload.message),
            backend="hosted",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/chat/auto", response_model=ChatResponse)
def chat_auto(payload: ChatRequest) -> ChatResponse:
    """Route automatically: use Ollama if it is reachable, else fall back to hosted.

    This is the production payoff of the unified contract: the SERVICE decides
    which backend answers, and the caller never has to know.  Probing /models is
    free (no token spend); only the winning backend actually generates text.
    """
    local = server_up(
        os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1"),
        os.getenv("LOCAL_API_KEY", "ollama"),
    )
    if local:
        return chat_local(payload)
    return chat_hosted(payload)