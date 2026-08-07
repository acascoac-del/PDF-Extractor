"""Script para descargar el modelo local de IA (Qwen 2.5 GGUF) desde Hugging Face.

Uso:
  python scripts/download_model.py [modelo]

Ejemplos:
  python scripts/download_model.py qwen7b   # Qwen 2.5 Coder 7B (Recomendado, ~4.7 GB)
  python scripts/download_model.py qwen3b   # Qwen 2.5 3B (~2.0 GB, para menos RAM)
  python scripts/download_model.py qwen1.5b # Qwen 2.5 1.5B (~1.1 GB, ultraligero)
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"

MODEL_URLS = {
    "qwen7b": (
        "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf",
    ),
    "qwen3b": (
        "qwen2.5-3b-instruct-q4_k_m.gguf",
        "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
    ),
    "qwen1.5b": (
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    ),
}


def download_progress(block_num: int, block_size: int, total_size: int):
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100.0, downloaded * 100 / total_size)
        mb_down = downloaded / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        sys.stdout.write(
            f"\rDescargando modelo: {percent:.1f}% ({mb_down:.1f} MB / {mb_total:.1f} MB)"
        )
        sys.stdout.flush()


def main():
    target_key = sys.argv[1].lower() if len(sys.argv) > 1 else "qwen7b"
    if target_key not in MODEL_URLS:
        print(f"Modelo desconocido '{target_key}'. Opciones disponibles: {list(MODEL_URLS.keys())}")
        sys.exit(1)

    filename, url = MODEL_URLS[target_key]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = MODELS_DIR / filename

    if target_path.exists() and target_path.stat().st_size > 100 * 1024 * 1024:
        print(f"✅ El modelo '{filename}' ya existe en {target_path}")
        return

    print(f"📥 Descargando {filename} desde Hugging Face...")
    print(f"🔗 URL: {url}")
    print(f"📁 Destino: {target_path}\n")

    try:
        urllib.request.urlretrieve(url, target_path, reporthook=download_progress)
        print(f"\n\n✨ Descarga completada exitosamente: {target_path}")
    except Exception as e:
        print(f"\n❌ Error al descargar el modelo: {e}")
        if target_path.exists():
            target_path.unlink()
        sys.exit(1)


if __name__ == "__main__":
    main()
