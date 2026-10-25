from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1000


class ModelRouter:
    """Central router for all LLM calls configured via config/models.yaml."""

    def __init__(self, config_path: Optional[str] = None, force_mock: bool = False):
        if config_path is None:
            # Look relative to project root
            base_dir = Path(__file__).resolve().parent.parent.parent
            config_path = str(base_dir / "config" / "models.yaml")

        self.config_path = config_path
        self.force_mock = force_mock
        self._configs: Dict[str, ModelConfig] = {}
        self._load_config()

    def _load_config(self):
        if not os.path.exists(self.config_path):
            # Fallback defaults if file missing
            self._configs = {
                "classifier": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
                "shallow": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
                "researcher": ModelConfig(provider="groq", model="llama-3.3-70b-versatile"),
                "clarifier": ModelConfig(provider="gemini", model="gemini-2.5-flash"),
                "planner": ModelConfig(provider="gemini", model="gemini-2.5-flash"),
                "verifier": ModelConfig(provider="gemini", model="gemini-2.5-flash"),
                "writer": ModelConfig(provider="gemini", model="gemini-2.5-flash"),
                "followup": ModelConfig(provider="gemini", model="gemini-2.5-flash"),
            }
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        for role, cfg in data.get("roles", {}).items():
            self._configs[role] = ModelConfig(
                provider=cfg.get("provider", "groq"),
                model=cfg.get("model", "llama-3.3-70b-versatile"),
                temperature=cfg.get("temperature", 0.0),
                max_tokens=cfg.get("max_tokens", 1000),
            )

    def get_model(self, role: str) -> Any:
        cfg = self._configs.get(role)
        if not cfg:
            cfg = ModelConfig(provider="groq", model="llama-3.3-70b-versatile")

        # In test mode or when explicitly forced, load MockLLM strictly from tests/mocks.py
        is_test_mode = (
            self.force_mock
            or os.environ.get("USE_MOCK_MODELS", "").lower() in ["1", "true", "yes"]
            or "PYTEST_CURRENT_TEST" in os.environ
        )

        if is_test_mode:
            try:
                from tests.mocks import MockLLM
                return MockLLM(role=role, config=cfg)
            except ImportError:
                pass

        # Non-test / production mode: real model execution is enforced
        if cfg.provider == "groq":
            groq_api_key = os.environ.get("GROQ_API_KEY")
            if not groq_api_key or groq_api_key.startswith("your_"):
                raise ValueError(
                    f"GROQ_API_KEY environment variable is required in non-test mode for role '{role}'. "
                    f"Please configure GROQ_API_KEY or run under test environment."
                )
            from langchain_groq import ChatGroq
            return ChatGroq(
                model_name=cfg.model,
                groq_api_key=groq_api_key,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )

        elif cfg.provider == "gemini":
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if not gemini_api_key or gemini_api_key.startswith("your_"):
                raise ValueError(
                    f"GEMINI_API_KEY environment variable is required in non-test mode for role '{role}'. "
                    f"Please configure GEMINI_API_KEY or run under test environment."
                )
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=cfg.model,
                google_api_key=gemini_api_key,
                temperature=cfg.temperature,
                max_output_tokens=cfg.max_tokens,
            )

        raise ValueError(f"Unsupported model provider: {cfg.provider}")

