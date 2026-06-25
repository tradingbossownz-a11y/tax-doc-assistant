"""
server.py — FastAPI backend for the Tax Document Assistant.

Routes:
  GET  /        → index.html
  POST /upload  → extract fields from a tax document (PDF or image)
  POST /chat    → run the agent tool-use loop; returns answer + tool calls
  GET  /health  → liveness check
"""

import base64
import json
import os
import sys
from typing import Any

import anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from prompts import SYSTEM_PROMPT
from tools import ANTHROPIC_TOOLS, execute_tool

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _load_env(path: str = ".env") -> None:
    """Minimal .env loader — no extra dependency needed."""
    try:
        with open(path) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_env()

_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    sys.exit(
        "ERROR: ANTHROPIC_API_KEY is not set.\n"
        "  1. Copy .env.example → .env\n"
        "  2. Paste your key from https://console.anthropic.com"
    )

client = anthropic.Anthropic(api_key=_api_key)
MODEL = "claude-sonnet-4-6"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

SUPPORTED_TYPES: dict[str, str] = {
    "application/pdf": "document",
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
}

app = FastAPI(title="Tax Document Assistant")

# ---------------------------------------------------------------------------
# In-memory state (one document at a time — no DB, no auth)
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {
    "document_block": None,
    "extraction": "",
    "filename": None,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_doc_block(media_type: str, data_b64: str) -> dict:
    kind = SUPPORTED_TYPES[media_type]
    return {
        "type": kind,
        "source": {"type": "base64", "media_type": media_type, "data": data_b64},
    }


def _block_to_dict(block: Any) -> dict:
    """Convert an SDK content block to a plain dict for re-use in the next API call."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return {"type": block.type}


def _run_tool_loop(messages: list) -> tuple[str, list[dict]]:
    """Drive the Claude tool-use loop until the model returns a final answer.

    Returns (final_text, tool_calls) where tool_calls is a list of
    {"name": str, "input": dict, "result": dict}.
    """
    tool_calls: list[dict] = []

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=ANTHROPIC_TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            text = next((b.text for b in response.content if b.type == "text"), "")
            if not text:
                text = "Lo siento, no pude generar una respuesta. Por favor, inténtalo de nuevo."
            return text, tool_calls

        # Append the assistant's tool-request turn
        messages.append({
            "role": "assistant",
            "content": [_block_to_dict(b) for b in response.content],
        })

        # Execute each tool and collect results
        tool_results: list[dict] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = execute_tool(block.name, block.input)
            tool_calls.append({
                "name": block.name,
                "input": dict(block.input),
                "result": result,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def root() -> FileResponse:
    return FileResponse("index.html")


@app.post("/upload")
def upload(file: UploadFile = File(...)):
    ct = (file.content_type or "").split(";")[0].strip()
    if ct not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported type '{ct}'. Please upload a PDF, JPEG, PNG, or WebP.",
        )

    raw = file.file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    data_b64 = base64.standard_b64encode(raw).decode()
    doc_block = _build_doc_block(ct, data_b64)

    extraction_messages = [
        {
            "role": "user",
            "content": [
                doc_block,
                {
                    "type": "text",
                    "text": (
                        "Extrae los campos principales de este documento: "
                        "tipo de documento, emisor, receptor, "
                        "importes (base imponible, tipo IVA, cuota IVA, total), "
                        "fechas relevantes, número de documento y modelo fiscal si aparece. "
                        "Responde con una lista breve y estructurada."
                    ),
                },
            ],
        }
    ]

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=extraction_messages,
        )
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")

    extraction = next((b.text for b in response.content if b.type == "text"), "")

    _state["document_block"] = doc_block
    _state["extraction"] = extraction
    _state["filename"] = file.filename

    return {"filename": file.filename, "extraction": extraction}


class HistoryItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryItem] = []


@app.post("/chat")
def chat(req: ChatRequest):
    if _state["document_block"] is None:
        raise HTTPException(
            status_code=400,
            detail="No document loaded. Please upload a document first.",
        )

    # Full message sequence every call:
    #   [user: document] → [assistant: extraction] → [history…] → [user: question]
    messages: list[dict] = [
        {
            "role": "user",
            "content": [
                _state["document_block"],
                {"type": "text", "text": "Aquí está el documento que vamos a analizar."},
            ],
        },
        {
            "role": "assistant",
            "content": _state["extraction"] or "He procesado el documento.",
        },
    ]

    for turn in req.history:
        if turn.role not in ("user", "assistant"):
            continue
        messages.append({"role": turn.role, "content": turn.content})

    messages.append({"role": "user", "content": req.message})

    try:
        answer, tool_calls = _run_tool_loop(messages)
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")

    return {"answer": answer, "tool_calls": tool_calls}


@app.get("/health")
def health():
    return {"ok": True, "document": _state["filename"]}
