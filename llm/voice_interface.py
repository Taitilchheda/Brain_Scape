"""
Brain_Scape — Voice Query Interface

Whisper ASR for audio transcription -> QA engine -> response.
TTS delegated to client browser speechSynthesis API.
Voice path latency target: < 3 seconds for most queries.
"""

import logging
import tempfile
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class VoiceInterface:
    """Handle voice input for scan-aware Q&A.

    Flow: Audio -> Whisper ASR -> text -> QA engine -> response
    TTS (text-to-speech) is delegated to the client browser's
    speechSynthesis API for zero server-side latency.
    """

    def __init__(
        self,
        qa_engine=None,
        whisper_model_size: str = "medium",
        whisper_device: str = "cpu",
    ):
        self.qa_engine = qa_engine
        self.whisper_model_size = whisper_model_size
        self.whisper_device = whisper_device
        self._whisper_model = None

    def _load_whisper(self):
        """Lazy-load Whisper model on first use."""
        if self._whisper_model is not None:
            return

        try:
            import whisper
            self._whisper_model = whisper.load_model(
                self.whisper_model_size, device=self.whisper_device
            )
            logger.info(f"Loaded Whisper {self.whisper_model_size} model on {self.whisper_device}")
        except ImportError:
            logger.warning(
                "openai-whisper not installed. Install with: pip install openai-whisper. "
                "Voice transcription will not be available."
            )
            self._whisper_model = None
        except Exception as e:
            logger.warning(f"Could not load Whisper model: {e}")
            self._whisper_model = None

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> Dict:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, FLAC, etc.)
            language: Language code (e.g., "en", "es", "fr"). Auto-detect if None.

        Returns:
            Dict with "text", "language", "segments", "duration" keys
        """
        self._load_whisper()

        if self._whisper_model is None:
            return {
                "text": "",
                "language": "unknown",
                "segments": [],
                "duration": 0,
                "error": "Whisper model not available. Install openai-whisper.",
            }

        if not os.path.exists(audio_path):
            return {
                "text": "",
                "language": "unknown",
                "segments": [],
                "duration": 0,
                "error": f"Audio file not found: {audio_path}",
            }

        try:
            import whisper

            options = {}
            if language:
                options["language"] = language

            result = self._whisper_model.transcribe(audio_path, **options)

            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", "unknown"),
                "segments": [
                    {
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", "").strip(),
                    }
                    for seg in result.get("segments", [])
                ],
                "duration": result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0,
            }

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return {
                "text": "",
                "language": "unknown",
                "segments": [],
                "duration": 0,
                "error": str(e),
            }

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        file_extension: str = ".wav",
        language: Optional[str] = None,
    ) -> Dict:
        """Transcribe audio from raw bytes.

        Args:
            audio_bytes: Raw audio data
            file_extension: File extension for temp file
            language: Language code

        Returns:
            Same dict as transcribe()
        """
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            return self.transcribe(temp_path, language=language)
        finally:
            os.unlink(temp_path)

    def voice_query(
        self,
        audio_path: str,
        analysis: Dict,
        language: Optional[str] = None,
    ) -> Dict:
        """Full voice query pipeline: audio -> text -> Q&A -> response.

        Args:
            audio_path: Path to audio file
            analysis: Analysis JSON for scan context
            language: Language code for transcription

        Returns:
            Dict with "transcription", "question", "answer", "citations", "confidence"
        """
        # Step 1: Transcribe
        transcription = self.transcribe(audio_path, language=language)

        if transcription.get("error"):
            return {
                "transcription": transcription,
                "question": "",
                "answer": "I couldn't understand your question. Please try again.",
                "citations": [],
                "confidence": 0.0,
                "error": transcription["error"],
            }

        question = transcription["text"]

        if not question:
            return {
                "transcription": transcription,
                "question": "",
                "answer": "I didn't catch that. Could you please repeat your question?",
                "citations": [],
                "confidence": 0.0,
            }

        # Step 2: Query the QA engine
        if self.qa_engine is None:
            return {
                "transcription": transcription,
                "question": question,
                "answer": "QA engine not available.",
                "citations": [],
                "confidence": 0.0,
                "error": "No QA engine configured",
            }

        qa_result = self.qa_engine.answer(question, analysis)

        return {
            "transcription": transcription,
            "question": question,
            "answer": qa_result.get("answer", ""),
            "citations": qa_result.get("citations", []),
            "confidence": qa_result.get("confidence", 0.0),
        }

    def voice_query_bytes(
        self,
        audio_bytes: bytes,
        analysis: Dict,
        file_extension: str = ".wav",
        language: Optional[str] = None,
    ) -> Dict:
        """Voice query from raw audio bytes.

        Same as voice_query but accepts bytes instead of file path.
        """
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            return self.voice_query(temp_path, analysis, language=language)
        finally:
            os.unlink(temp_path)

    @staticmethod
    def get_tts_instructions() -> Dict:
        """Return instructions for client-side TTS using browser speechSynthesis.

        The server does NOT do text-to-speech. The client should use
        the Web Speech API (speechSynthesis) for zero-latency playback.
        """
        return {
            "method": "browser_speech_synthesis",
            "api": "window.speechSynthesis",
            "instructions": (
                "Use the browser's built-in speechSynthesis API for TTS. "
                "This provides zero server-side latency and works offline. "
                "Example JavaScript:\n"
                "const utterance = new SpeechSynthesisUtterance(responseText);\n"
                "utterance.rate = 0.9;\n"
                "utterance.pitch = 1.0;\n"
                "speechSynthesis.speak(utterance);"
            ),
            "supported_languages": ["en-US", "en-GB", "es-ES", "fr-FR", "de-DE", "it-IT", "pt-BR", "zh-CN", "ja-JP"],
            "latency_target_ms": 0,  # Client-side, no server latency
        }