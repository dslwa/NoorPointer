"""Pre-fetch Hugging Face models at Docker build time so the container starts offline."""

from huggingface_hub import snapshot_download

from app.config import Settings

if __name__ == "__main__":
    snapshot_download(Settings.from_env().pi_model)
