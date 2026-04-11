from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_title: str = "WayFinder: Your Travel Planning Assistant"
    model_name: str = "Qwen/Qwen2.5-1.5B-Instruct"
    max_new_tokens: int = 200
    # Agent loop: tool-calling turns need more room than a single chat reply.
    agent_max_new_tokens: int = 512
    agent_max_steps: int = 6
    agent_temperature: float = 0.3


settings = Settings()
