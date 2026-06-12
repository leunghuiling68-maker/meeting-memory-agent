"""ASR placeholders.

MVP does not call third-party speech recognition APIs. Future versions can
replace these functions with Whisper, cloud ASR, or local model adapters.
"""


def transcribe_audio_placeholder(file_path: str) -> str:
    """Return a placeholder transcript for an uploaded audio file."""
    return f"[ASR placeholder] audio file queued for transcription: {file_path}"

