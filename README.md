# Tax Document Assistant 🇪🇸

A focused **GenAI agent** that reads a single Spanish tax document (invoice, payslip, *certificado de retenciones*…) and answers questions about it — calling real tools to compute IVA and look up filing deadlines as it reasons.

> Built to demonstrate **agentic tool-calling** and **grounded document Q&A** with the Anthropic API.

## What makes it an *agent*

Most "AI apps" do one prompt → one answer. This one runs a proper **tool-use loop**: Claude reads the document, and when a question needs a precise number or date, it calls a Python function, gets the result back, and continues reasoning. You can see each tool call in the UI.

Tools the model can call:
- **`calcular_iva(base, tipo)`** — exact IVA cuota and total.
- **`proximo_plazo_modelo(modelo)`** — next AEAT filing deadline for a modelo (303, 130, 111, 100…) and days remaining.
- **`buscar_modelo(modelo)`** — name and frequency of a modelo.

The tool logic lives in `tools.py`, decoupled from the agent, so the tax rules stay readable and testable.

## How it works

1. Upload one PDF or image → it's sent to Claude as a document/image block and the key fields are extracted.
2. Ask questions in natural language → answers are **grounded only in that document** (a minimal RAG pattern).
3. When precision is needed, Claude calls a tool and uses the real result.

## Tech stack

- **Python** · **FastAPI** (backend + agent loop) · **Anthropic Python SDK** (tool use, document input)
- Vanilla HTML/JS chat frontend — no framework needed.

## Run it

See **[SETUP.md](SETUP.md)**. Short version:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
uvicorn server:app --reload
```

## Disclaimer

This tool helps read and understand documents; it does not file taxes or give binding advice. Deadlines and IVA rates in `tools.py` are marked `# VERIFY` and must be checked against current AEAT rules.

## License

MIT
