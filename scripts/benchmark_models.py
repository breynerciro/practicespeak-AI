#!/usr/bin/env python3
"""Benchmark de modelos Ollama con el tuning real de PracticeSpeak AI.

Simula el payload de producción (system prompt inmersivo, format json,
think off, temperature 0.8, repeat_penalty 1.15, num_predict configurado)
contra varios modelos y mide:

- TTFT:  tiempo hasta el primer token (lo que percibe el usuario en streaming)
- Total: tiempo hasta la respuesta completa
- Tok/s: velocidad sostenida de generación
- JSON:  si la respuesta completa es JSON válido y trae reply/corrections

Uso:  python3 scripts/benchmark_models.py [modelo: prompts] ...
      python3 scripts/benchmark_models.py            # los de por defecto
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

# Reutiliza el prompt y opciones EXACTOS de producción
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import ai, config  # noqa: E402

OLLAMA_URL = config.OLLAMA_BASE_URL + "/api/chat"

# Tres escenarios representativos de una sesión real:
# 1) start  → saludo inicial corto
# 2) continue con historial (turno medio de conversación)
# 3) continue con historial largo (peor caso: 12 turnos + lista de preguntas)


def escenarios() -> list[tuple[str, list[dict]]]:
    lang = ai._lang_name("en")
    system = ai.IMMERSIVE_SYSTEM.replace("__LANG__", lang)
    start_user = (
        "BEGIN a new immersive session. The topic for this session is 'travel'.\n"
        "Talk ONLY about 'travel'; do not pick a different topic.\n"
        "Greet the student briefly and ask your first engaging question about 'travel' in English. Keep it short."
    )
    continue_user = (
        "The student said (voice transcription): i travel to beach last summer with my family "
        "and we eated paella every day\n\n"
        "Questions you ALREADY asked in this conversation (do NOT repeat them and do NOT "
        "rephrase them; ask something NEW that explores a different angle):\n"
        "- What's the most memorable trip you've ever taken?"
    )
    historial = []
    for i in range(6):
        historial.append({"role": "user", "content": f"i like the beach number {i} very much"})
        historial.append({"role": "assistant", "content": f"That sounds fun! Tell me more about your trip number {i}. Do you prefer the sea or the mountains?"})
    return [
        ("start (saludo inicial)", [
            {"role": "system", "content": system},
            {"role": "user", "content": start_user},
        ]),
        ("continue (turno medio)", [
            {"role": "system", "content": system},
            *historial[:4],
            {"role": "user", "content": continue_user},
        ]),
        ("continue (historial largo)", [
            {"role": "system", "content": system},
            *historial,
            {"role": "user", "content": continue_user},
        ]),
    ]


async def medir(client: httpx.AsyncClient, model: str, messages: list[dict], num_predict: int) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0.8,
            "top_p": 0.9,
            "repeat_penalty": 1.15,
            "num_predict": num_predict,
        },
    }
    t0 = time.perf_counter()
    ttft = None
    buffer = ""
    eval_tokens = None
    async with client.stream("POST", OLLAMA_URL, json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                return {"error": chunk["error"]}
            delta = (chunk.get("message") or {}).get("content") or ""
            if delta:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                buffer += delta
            if chunk.get("done"):
                eval_tokens = chunk.get("eval_count")
                total_ns = chunk.get("total_duration", 0)
                eval_ns = chunk.get("eval_duration", 0)
    total = time.perf_counter() - t0
    tok_s = (eval_tokens / (eval_ns / 1e9)) if eval_tokens and eval_ns else None
    try:
        data = json.loads(buffer)
        json_ok = isinstance(data, dict) and "reply" in data and isinstance(data.get("corrections"), list)
    except json.JSONDecodeError:
        json_ok = False
    return {
        "ttft": ttft,
        "total": total,
        "tok_s": tok_s,
        "chars": len(buffer),
        "json_ok": json_ok,
        "reply": (data.get("reply", "") if json_ok else buffer[:80]),
    }


async def bench(modelo: str, rondas: int, num_predict: int) -> dict:
    resultados: dict[str, list[dict]] = {}
    async with httpx.AsyncClient(timeout=600) as client:
        # calentamiento: carga el modelo en GPU/RAM una sola vez
        await medir(client, modelo, escenarios()[0][1], 16)
        for nombre, msgs in escenarios():
            resultados[nombre] = []
            for _ in range(rondas):
                resultados[nombre].append(await medir(client, modelo, msgs, num_predict))
    return resultados


def resumen(nombre: str, r: dict) -> None:
    print(f"\n=== {nombre} ===")
    for esc, runs in r.items():
        ok = [x for x in runs if "error" not in x and x.get("ttft")]
        if not ok:
            print(f"  {esc}: ERROR {runs[0].get('error', '?')[:80]}")
            continue
        ttft = sorted(x["ttft"] for x in ok)[len(ok) // 2]
        total = sorted(x["total"] for x in ok)[len(ok) // 2]
        tok = sorted(x["tok_s"] for x in ok if x["tok_s"])[len(ok) // 2]
        chars = max(x["chars"] for x in ok)
        json_pct = 100 * sum(1 for x in ok if x["json_ok"]) // len(ok)
        print(f"  {esc}:")
        print(f"    TTFT mediana: {ttft*1000:6.0f} ms | total mediana: {total:5.2f} s | gen: {tok:5.1f} tok/s | JSON válido: {json_pct}% | máx {chars} chars")
        ejemplo = ok[0]["reply"]
        print(f"    reply: {ejemplo[:90]!r}")


async def main() -> None:
    # formato: modelo[/num_predict]; rondas fijas = 3
    # (la barra evita chocar con el ':' de las etiquetas de Ollama, p. ej. qwen3:1.7b)
    modelos = sys.argv[1:] or [config.OLLAMA_MODEL, "qwen3:4b"]
    rondas = 3
    print("Payload de producción: format=json, think=false, temp=0.8, repeat_penalty=1.15")
    print(f"Rondas por escenario: {rondas} (tras calentamiento)\n")
    for spec in modelos:
        if "/" in spec:
            modelo, np_ = spec.rsplit("/", 1)
            num_predict = int(np_)
        else:
            modelo, num_predict = spec, config.NUM_PREDICT
        try:
            r = await bench(modelo, rondas, num_predict)
            resumen(f"{modelo} (num_predict={num_predict})", r)
        except httpx.HTTPError as e:
            print(f"\n=== {modelo} ===\n  FALLO: {e}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
