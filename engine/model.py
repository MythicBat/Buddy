import json, subprocess, textwrap

MODEL = "llama3.1"
# If you added Ollama to PATH, you can just use "ollama"
OLLAMA = r"C:\Users\Alin Merchant\AppData\Local\Programs\Ollama\ollama.exe"

def _run_ollama(prompt: str) -> str:
    proc = subprocess.run([OLLAMA, "run", MODEL], input=prompt.encode(), capture_output=True)
    return proc.stdout.decode().strip()

def ask_llm(prompt: str) -> str:
    return _run_ollama(prompt)

def ask_llm_json(system_goal: str, user_task: str, schema_hint: str) -> dict:
    """Ask model to return STRICT JSON. We wrap with clear instructions and fallback parse."""
    prompt = textwrap.dedent(f"""
    You are Buddy's reasoning engine.
    Goal: {system_goal}

    IMPORTANT:
    - Return ONLY a JSON object with double-quoted keys/strings.
    - Do not include any explanation outside JSON.
    JSON schema (informal): {schema_hint}

    User task:
    {user_task}
    """).strip()
    out = _run_ollama(prompt).strip()
    # best-effort JSON recovery
    try:
        # Trim code fences if any
        if out.startswith("```"):
            out = out.split("```")[1]
        return json.loads(out)
    except Exception:
        return {"error": True, "raw": out}