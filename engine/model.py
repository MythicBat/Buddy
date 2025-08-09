import subprocess

MODEL = "llama3.1"
OLLAMA_PATH = r"C:\Users\Alin Merchant\AppData\Local\Programs\Ollama\ollama.exe"

def ask_llm(prompt: str) -> str:
    proc = subprocess.run(
        [OLLAMA_PATH, "run", MODEL],
        input=prompt.encode(),
        capture_output=True
    )
    return proc.stdout.decode().strip()