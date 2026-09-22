from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _require_non_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("no puede estar vacío")
    return value


# Idiomas de práctica soportados (voces edge-tts + Whisper disponibles).
# Mantener en síncrono con config.SUPPORTED_LANGUAGES.
Language = Literal["en", "pt", "fr", "de", "it", "es", "ru", "zh"]


class Turn(BaseModel):
    """Un turno de la conversación dentro de `history`."""

    role: Literal["user", "assistant"]
    content: str = ""


class ChatRequest(BaseModel):
    language: Language = "en"
    message: str
    history: list[Turn] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, value: str) -> str:
        return _require_non_empty(value)


class GrammarRequest(BaseModel):
    language: Language = "en"
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, value: str) -> str:
        return _require_non_empty(value)


class ImmersiveRequest(BaseModel):
    language: Language = "en"
    mode: Literal["start", "continue"] = "start"
    topic: str = ""
    message: str = ""
    history: list[Turn] = Field(default_factory=list)
    session_id: int | None = None  # devuelto por /start y reenviado en /continue
    profile_id: int | None = None  # apodo anónimo al que atribuir la sesión

    @model_validator(mode="after")
    def message_required_when_continue(self) -> "ImmersiveRequest":
        if self.mode == "continue" and not self.message.strip():
            raise ValueError("Empty message")
        return self


class ProfileCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_ok(cls, value: str) -> str:
        return _require_non_empty(value)
