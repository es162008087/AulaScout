"""Tests sin red: settings, prompts y payloads."""

import os

import pytest

from types import SimpleNamespace

from src.config import load_settings
from src.image import build_ficha_prompt, extract_image_b64
from src.sam import (
    FALLBACK_MATERIALS,
    build_sam_payload,
    clean_special_tokens,
    parse_materials,
)
from src.spark import build_planeacion_prompt
from src.voice import (
    DEMO_TRANSCRIPTION,
    parse_materiales_desde_voz,
)


def test_load_settings_falla_sin_key(monkeypatch):
    # find_dotenv parte del archivo que llama (src/config.py), no del cwd:
    # hay que neutralizarlo para probar "sin key" aunque exista .env real.
    monkeypatch.setattr("src.config.load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MODEL_API_KEY"):
        load_settings()


def test_load_settings_ok(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("META_API_BASE_URL", "https://api.meta.ai/v1/")
    settings = load_settings()
    assert settings.api_key == "test-key"
    assert settings.base_url == "https://api.meta.ai/v1"


def test_prompt_planeacion_pide_3_actividades():
    prompt = build_planeacion_prompt(["bloques", "pelotas"])
    assert "3 actividades" in prompt
    assert "bloques" in prompt and "pelotas" in prompt
    assert "SEP" in prompt


def test_prompt_planeacion_sin_materiales():
    assert "materiales basicos" in build_planeacion_prompt([])


def test_ficha_prompt_no_vacio():
    assert len(build_ficha_prompt("## Actividad 1\nJuego libre")) > 20


def test_sam_payload_base64():
    payload = build_sam_payload(b"\x89PNG")
    assert payload["image_b64"]


def test_parse_materials_extrae_output_text():
    output = [
        {"type": "other", "content": []},
        {
            "type": "message",
            "content": [
                {"type": "output_text", "text": "bloques, tapete\n- juguetes"},
            ],
        },
    ]
    assert parse_materials(output) == ["bloques", "tapete", "juguetes"]
    assert parse_materials([]) == []
    assert parse_materials(None) == []


def test_extract_image_b64_quita_prefijo_data():
    output = [
        {"type": "message", "content": []},
        {"type": "image_generation_call", "result": "data:image/png;base64,QUJD"},
    ]
    assert extract_image_b64(output) == "QUJD"
    assert extract_image_b64([]) == ""


def test_clean_special_tokens():
    raw = "bloques <|endoftext|> tapete <|im_end|>"
    cleaned = clean_special_tokens(raw)
    assert "<|" not in cleaned
    assert "bloques" in cleaned and "tapete" in cleaned


def test_parse_materials_ignora_tokens_especiales():
    output = [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "bloques, <|x|> tapete"}],
        }
    ]
    assert parse_materials(output) == ["bloques", "tapete"]


def test_sam_fallback_lista_fija_si_todo_falla(monkeypatch, tmp_path):
    import src.sam as sam_mod

    class FakeClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("sin red")

    monkeypatch.setattr(sam_mod, "OpenAI", FakeClient)
    foto = tmp_path / "salon.jpg"
    foto.write_bytes(b"\xff\xd8fake")
    settings = SimpleNamespace(base_url="https://x", api_key="k")
    assert sam_mod.detect_materials(foto, settings) == FALLBACK_MATERIALS


def test_spark_lanza_valueerror_si_vacio(monkeypatch):
    import src.spark as spark_mod

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            msg = SimpleNamespace(content="")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(spark_mod, "OpenAI", FakeClient)
    settings = SimpleNamespace(base_url="https://x", api_key="k")
    with pytest.raises(ValueError, match="Spark sin respuesta"):
        spark_mod.generate_planeacion(["bloques"], settings)
    assert len(calls) == 3  # 1 intento + 2 reintentos


def test_parse_materiales_desde_voz_mapea_keywords():
    mats = parse_materiales_desde_voz(DEMO_TRANSCRIPTION)
    assert mats == [
        "tapete de foami multicolor",
        "bloques de madera de colores",
        "canasta de pelotas suaves",
        "libros infantiles de tela",
    ]
    assert parse_materiales_desde_voz("hola, sin materiales aqui") == []


def test_transcribir_audio_fallback_demo(monkeypatch, tmp_path):
    import src.voice as voice_mod

    def fake_post(*args, **kwargs):
        raise RuntimeError("sin red")

    monkeypatch.setattr(voice_mod.requests, "post", fake_post)
    audio = tmp_path / "nota.m4a"
    audio.write_bytes(b"fake-audio")
    settings = SimpleNamespace(base_url="https://x", api_key="k")
    assert voice_mod.transcribir_audio(audio, settings) == DEMO_TRANSCRIPTION


def test_sam_reintenta_con_backoff(monkeypatch, tmp_path):
    import src.sam as sam_mod

    calls = []
    sleeps = []
    output = [
        {"type": "message", "content": [{"type": "output_text", "text": "bloques, tapete"}]}
    ]

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                raise TimeoutError("boom")
            return SimpleNamespace(output=output)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(sam_mod, "OpenAI", FakeClient)
    monkeypatch.setattr(sam_mod.time, "sleep", sleeps.append)
    foto = tmp_path / "salon.jpg"
    foto.write_bytes(b"\xff\xd8fake")
    settings = SimpleNamespace(base_url="https://x", api_key="k")
    assert sam_mod.detect_materials(foto, settings) == ["bloques", "tapete"]
    assert sleeps == [2, 4]
