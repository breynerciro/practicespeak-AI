import os
import re
import tempfile
from difflib import SequenceMatcher

from . import config

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(config.WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    text = " ".join(text.split())
    return text


def transcribe(audio_bytes: bytes, language: str) -> str:
    model = _get_model()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        segments, _info = model.transcribe(tmp_path, language=language, beam_size=config.WHISPER_BEAM)
        return " ".join(s.text.strip() for s in segments).strip()
    finally:
        os.unlink(tmp_path)


def evaluate(expected: str, transcript: str, language: str) -> dict:
    exp_tokens = _normalize(expected).split()
    trs_tokens = _normalize(transcript).split()
    if not exp_tokens:
        return {"score": 100, "transcript": transcript, "feedback": [], "missing": []}
    if not trs_tokens:
        return {"score": 0, "transcript": transcript, "feedback": [], "missing": exp_tokens}

    exp_str = " ".join(exp_tokens)
    trs_str = " ".join(trs_tokens)
    ratio = SequenceMatcher(None, exp_str, trs_str).ratio()

    sm = SequenceMatcher(None, exp_tokens, trs_tokens)
    missing = []
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag == "delete":
            missing.extend(exp_tokens[i1:i2])
    missing = list(dict.fromkeys(missing))

    score = round(ratio * 100)
    feedback = []
    if score >= 90:
        feedback.append("Excellent pronunciation, keep going!")
    elif score >= 70:
        feedback.append("Good. Try to be more precise on the words below.")
    elif score >= 40:
        feedback.append("Not bad, but several words need work.")
    else:
        feedback.append("Careful: repeat the sentence slowly and pay attention to each word.")

    if missing:
        feedback.append(f"Words to practice: {', '.join(missing)}")

    return {
        "score": max(0, min(100, score)),
        "transcript": transcript,
        "feedback": feedback,
        "missing": missing,
    }
