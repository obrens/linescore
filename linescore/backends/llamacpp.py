"""Backend using llama-cpp-python for local inference."""

import threading
from pathlib import Path

MODELS_DIR = Path.home() / ".linescore" / "models"
DEFAULT_MODEL = MODELS_DIR / "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"

# HuggingFace coordinates for the default model
DEFAULT_MODEL_REPO = "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"


def download_default_model() -> Path:
    """Download the default model from HuggingFace. Returns the local path."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError(
            "huggingface-hub is required to download models. "
            "This should have been installed with: linescore install llamacpp"
        )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {DEFAULT_MODEL_FILE} (~1 GB)...")
    path = hf_hub_download(
        repo_id=DEFAULT_MODEL_REPO,
        filename=DEFAULT_MODEL_FILE,
        local_dir=str(MODELS_DIR),
    )
    return Path(path)


class LlamaCppBackend:
    """Runs inference locally via llama-cpp-python bindings."""

    def __init__(
        self,
        model_path: str | None = None,
        n_ctx: int = 8192,
        max_tokens: int = 256,
    ):
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "The llamacpp backend requires llama-cpp-python. "
                "Install it with: linescore install llamacpp"
            )

        if model_path is None:
            if not DEFAULT_MODEL.exists():
                raise FileNotFoundError(
                    f"No default model found at {DEFAULT_MODEL}. "
                    "Run: linescore install llamacpp"
                )
            model_path = str(DEFAULT_MODEL)

        self._llm = Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
        self._n_ctx = n_ctx
        self._max_tokens = max_tokens
        self._lock = threading.Lock()

    def complete(self, prompt: str) -> str:
        # Rough guard: ~3 chars per token. If prompt is too long, skip rather than segfault.
        estimated_tokens = len(prompt) // 3
        if estimated_tokens + self._max_tokens > self._n_ctx:
            return ""

        # llama-cpp-python is not thread-safe — serialize all calls
        with self._lock:
            output = self._llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._max_tokens,
            )
        return output["choices"][0]["message"]["content"]
