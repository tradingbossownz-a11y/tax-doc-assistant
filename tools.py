"""
tools.py — Agent tools for the Tax Document Assistant.

This is the DOMAIN layer the AI agent calls. The model decides *when* to call
these; the logic here decides *what they return*. Tax specifics are marked
# VERIFY — review them (deadlines, IVA types) against current AEAT rules.

Pure-Python, no external imports, so it can be unit-tested on its own.
server.py imports: from tools import ANTHROPIC_TOOLS, execute_tool
"""

from datetime import date

# ---------------------------------------------------------------------------
# Modelo catalog (mirrors the Asesoría NL app). Deadlines: m=month, d=day,
# fy=fiscal-year offset (the period belongs to year+fy, filed on that date).
# # VERIFY against the current AEAT calendar each year.
# ---------------------------------------------------------------------------
MODELOS = {
    "303": {"name": "IVA trimestral",        "freq": "trimestral", "dl": [{"p": "1T","m":4,"d":20},{"p":"2T","m":7,"d":20},{"p":"3T","m":10,"d":20},{"p":"4T","m":1,"d":30,"fy":-1}]},
    "390": {"name": "Resumen anual IVA",     "freq": "anual",      "dl": [{"p":"Año","m":1,"d":30,"fy":-1}]},
    "130": {"name": "IRPF pago fraccionado", "freq": "trimestral", "dl": [{"p":"1T","m":4,"d":20},{"p":"2T","m":7,"d":20},{"p":"3T","m":10,"d":20},{"p":"4T","m":1,"d":30,"fy":-1}]},
    "131": {"name": "IRPF módulos",          "freq": "trimestral", "dl": [{"p":"1T","m":4,"d":20},{"p":"2T","m":7,"d":20},{"p":"3T","m":10,"d":20},{"p":"4T","m":1,"d":30,"fy":-1}]},
    "111": {"name": "Retenciones trabajo",   "freq": "trimestral", "dl": [{"p":"1T","m":4,"d":20},{"p":"2T","m":7,"d":20},{"p":"3T","m":10,"d":20},{"p":"4T","m":1,"d":20,"fy":-1}]},
    "190": {"name": "Resumen anual 111",     "freq": "anual",      "dl": [{"p":"Año","m":1,"d":31,"fy":-1}]},
    "115": {"name": "Retenciones alquileres","freq": "trimestral", "dl": [{"p":"1T","m":4,"d":20},{"p":"2T","m":7,"d":20},{"p":"3T","m":10,"d":20},{"p":"4T","m":1,"d":20,"fy":-1}]},
    "180": {"name": "Resumen anual 115",     "freq": "anual",      "dl": [{"p":"Año","m":1,"d":31,"fy":-1}]},
    "349": {"name": "Intracomunitarias",     "freq": "trimestral", "dl": [{"p":"1T","m":4,"d":20},{"p":"2T","m":7,"d":20},{"p":"3T","m":10,"d":20},{"p":"4T","m":1,"d":30,"fy":-1}]},
    "347": {"name": "Operaciones terceros",  "freq": "anual",      "dl": [{"p":"Año","m":2,"d":28,"fy":-1}]},
    "100": {"name": "Renta (IRPF)",          "freq": "anual",      "dl": [{"p":"Año","m":6,"d":30,"fy":-1}]},
    "714": {"name": "Patrimonio",            "freq": "anual",      "dl": [{"p":"Año","m":6,"d":30,"fy":-1}]},
    "200": {"name": "Impuesto Sociedades",   "freq": "anual",      "dl": [{"p":"Año","m":7,"d":25,"fy":-1}]},
}

# Valid IVA rates in Spain. # VERIFY current rates.
IVA_TIPOS = [21, 10, 4, 0]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def calcular_iva(base, tipo):
    base = float(base)
    tipo = float(tipo)
    cuota = round(base * tipo / 100, 2)
    return {"base": round(base, 2), "tipo": tipo, "cuota": cuota, "total": round(base + cuota, 2)}


def proximo_plazo_modelo(modelo, hoy=None):
    modelo = str(modelo).strip()
    if modelo not in MODELOS:
        return {"error": f"Modelo {modelo} desconocido", "modelos_validos": list(MODELOS)}
    today = date.fromisoformat(hoy) if hoy else date.today()
    cands = []
    for dl in MODELOS[modelo]["dl"]:
        for y in (today.year, today.year + 1):
            try:
                fecha = date(y, dl["m"], dl["d"])
            except ValueError:
                continue
            if fecha >= today:
                cands.append((fecha, dl["p"], y + dl.get("fy", 0)))
    if not cands:
        return {"error": "No upcoming deadline found"}
    cands.sort()
    fecha, periodo, fy = cands[0]
    return {
        "modelo": modelo,
        "nombre": MODELOS[modelo]["name"],
        "periodo": periodo,
        "ejercicio": fy,
        "fecha_limite": fecha.isoformat(),
        "dias_restantes": (fecha - today).days,
    }


def buscar_modelo(modelo):
    modelo = str(modelo).strip()
    if modelo not in MODELOS:
        return {"error": f"Modelo {modelo} desconocido", "modelos_validos": list(MODELOS)}
    m = MODELOS[modelo]
    return {"modelo": modelo, "nombre": m["name"], "frecuencia": m["freq"]}


# ---------------------------------------------------------------------------
# Tool schemas exposed to Claude (Anthropic tool-use format)
# ---------------------------------------------------------------------------
ANTHROPIC_TOOLS = [
    {
        "name": "calcular_iva",
        "description": "Calcula la cuota de IVA y el total a partir de una base imponible y un tipo de IVA (21, 10, 4 o 0).",
        "input_schema": {
            "type": "object",
            "properties": {
                "base": {"type": "number", "description": "Base imponible en euros, sin IVA"},
                "tipo": {"type": "number", "description": "Tipo de IVA en %, p.ej. 21, 10, 4 o 0"},
            },
            "required": ["base", "tipo"],
        },
    },
    {
        "name": "proximo_plazo_modelo",
        "description": "Devuelve la próxima fecha límite de presentación de un modelo fiscal español (303, 130, 111, 100, etc.) y los días que faltan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "modelo": {"type": "string", "description": "Código del modelo, p.ej. '303'"},
            },
            "required": ["modelo"],
        },
    },
    {
        "name": "buscar_modelo",
        "description": "Devuelve el nombre y la frecuencia de un modelo fiscal español dado su código.",
        "input_schema": {
            "type": "object",
            "properties": {
                "modelo": {"type": "string", "description": "Código del modelo, p.ej. '111'"},
            },
            "required": ["modelo"],
        },
    },
]

_DISPATCH = {
    "calcular_iva": lambda i: calcular_iva(i["base"], i["tipo"]),
    "proximo_plazo_modelo": lambda i: proximo_plazo_modelo(i["modelo"]),
    "buscar_modelo": lambda i: buscar_modelo(i["modelo"]),
}


def execute_tool(name, tool_input):
    """Run a tool by name with the input dict from Claude. Returns a dict."""
    if name not in _DISPATCH:
        return {"error": f"Unknown tool: {name}"}
    try:
        return _DISPATCH[name](tool_input)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
