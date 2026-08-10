from dataclasses import dataclass
from typing import Any
from aegis.packages.aegis import LLMProvider

@dataclass
class GroqProvider(LLMProvider):
    """A minimal provider for the demo."""
    model_id: str = "openai/gpt-oss-120b"
    
    async def generate(self, prompt: str, **kwargs) -> Any:
        pass
