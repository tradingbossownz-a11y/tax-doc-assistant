# Setup & testing

## 1. Python
Need **Python 3.12**. Check: `python3.12 --version`.

## 2. Install
```bash
python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. API key
```bash
cp .env.example .env
```
Edit `.env` and paste your key from https://console.anthropic.com (separate from Claude Pro, billed per use).

## 4. Run
```bash
uvicorn server:app --reload
```
Open the URL it prints (usually http://127.0.0.1:8000).

## 5. Test the agent
- [ ] Upload a sample invoice → fields are extracted.
- [ ] Ask "¿Cuánto IVA lleva esta factura?" → watch it call **calcular_iva**.
- [ ] Ask "¿Cuándo vence el próximo 303?" → watch it call **proximo_plazo_modelo**.
- [ ] Ask something not in the document → it should say it doesn't know, not invent.

## Quick tool test (no key needed)
```bash
python -c "import tools; print(tools.proximo_plazo_modelo('303'))"
```
