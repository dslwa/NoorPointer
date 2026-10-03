"""Pre-fetch Hugging Face models at Docker build time so the container starts offline."""

from huggingface_hub import snapshot_download

from app.config import Settings

if __name__ == "__main__":
    # transformers loads the safetensors weights; the repo's ONNX export would only bloat the image
    snapshot_download(Settings.from_env().pi_model, ignore_patterns=["onnx/*", "*.onnx"])
