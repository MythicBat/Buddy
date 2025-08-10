import os, wave, json
import pyttsx3
import soundfile as sf
from vosk import Model, KaldiRecognizer

# ---- STT (Offline) ----
_models_cache = {}

def _get_vosk_model(model_dir: str):
    global _models_cache
    if model_dir not in _models_cache:
        if not os.path.isdir(model_dir):
            raise RuntimeError(f"Vosk model not found at {model_dir}")
        _models_cache[model_dir] = Model(model_dir)
    return _models_cache[model_dir]

def stt_transcribe_wav(path_wav: str, model_dir: str) -> str:
    """Transcribe a mono 16k WAV file using Vosk offline."""
    model = _get_vosk_model(model_dir)
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(False)

    # Ensure the WAV is 16k mono PCM; if not, convert via soundfile
    data, samplerate = sf.read(path_wav)
    if samplerate != 16000 or (len(data.shape) > 1 and data.shape[1] != 1):
        # convert to mono 16k
        import numpy as np
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        import resampy
        data = resampy.resample(data, samplerate, 16000)
        sf.write(path_wav, data, 16000, subtype='PCM_16')
    
    wf = wave.open(path_wav, "rb")
    result = ""
    while True:
        buf = wf.readframes(4000)
        if len(buf) == 0:
            break
        if rec.AcceptWaveform(buf):
            part = json.loads(rec.Result()).get("text", "")
            result += (" " + part)
    final = json.loads(rec.FinalResult()).get("text", "")
    result = (result + " " + final).strip()
    return result

# ---- TTS (Offline) ----
_tts_engine = None

def _tts():
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = pyttsx3.init()
        # tweak rate/voice here if you like
        _tts_engine.setProperty("rate", 180)
    return _tts_engine

def tts_save_wav(text: str, out_path: str):
    eng = _tts()
    eng.save_to_file(text, out_path)
    eng.runAndWait()
    return out_path
