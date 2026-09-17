"""FastAPI service that wraps a local or hosted model behind one HTTP contract.

Two endpoints, one shared model-calling function:

    POST /chat/local   -> Ollama on this machine
    POST /chat/hosted  -> whatever hosted provider is configured in .env

Both endpoints build the same Pydantic request/response shape and both call
the SAME ``ask_model`` function; only the client and the model name differ.
That symmetry is the whole point of today's build (see app/model_client.py).
"""

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.model_client import ask_model, get_client

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


@app.get("/")
def root() -> dict:
    return {
        "service": "local-and-hosted-llm-api",
        "endpoints": ["/chat/local", "/chat/hosted"],
        "docs": "/docs",
    }


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