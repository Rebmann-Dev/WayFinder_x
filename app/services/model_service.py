import os
from threading import Thread
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

from core.config import settings


class ModelService:
    def __init__(self) -> None:
        self.device = self._select_device()
        dtype = torch.float16 if self.device.type == "cuda" else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(settings.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            settings.model_name,
            dtype=dtype,
        ).to(self.device)
        self.model.eval()

    @staticmethod
    def _select_device() -> torch.device:
        forced = os.getenv("WAYFINDER_DEVICE", "").strip()
        if forced:
            return torch.device(forced)
        if torch.cuda.is_available():
            return torch.device("cuda")
        # MPS can hit allocator limits on some Macs with long tool prompts; opt-in only.
        if os.getenv("WAYFINDER_USE_MPS", "").lower() in ("1", "true", "yes"):
            if torch.backends.mps.is_available():
                return torch.device("mps")
        return torch.device("cpu")

    def stream_agent_turn(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ):
        """Stream one assistant generation (tool-aware template). Yields decoded text chunks."""
        text = self.tokenizer.apply_chat_template(
            messages,
            tools=tools,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            add_special_tokens=False,
        ).to(self.device)

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        gen_kwargs: dict[str, Any] = {
            **inputs,
            "max_new_tokens": settings.agent_max_new_tokens,
            "do_sample": True,
            "temperature": settings.agent_temperature,
            "pad_token_id": self.tokenizer.eos_token_id,
            "streamer": streamer,
        }

        def _run() -> None:
            with torch.no_grad():
                self.model.generate(**gen_kwargs)

        thread = Thread(target=_run)
        thread.start()

        for chunk in streamer:
            if chunk:
                yield chunk

        thread.join()

    def stream_reply(self, messages: list[dict[str, str]]):
        inputs = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.device)

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        generation_kwargs = {
            "input_ids": inputs,
            "max_new_tokens": settings.max_new_tokens,
            "do_sample": True,
            "temperature": 0.7,
            "pad_token_id": self.tokenizer.eos_token_id,
            "streamer": streamer,
        }

        def _run() -> None:
            with torch.no_grad():
                self.model.generate(**generation_kwargs)

        thread = Thread(target=_run)
        thread.start()

        for chunk in streamer:
            if chunk:
                yield chunk

        thread.join()

    def generate_reply_from_text(self, user_message: str) -> str:
        messages = [
            {
                "role": "system",
                "content": "You are a professional AI travel agent. Only answer travel-related questions.",
            },
            {"role": "user", "content": user_message},
        ]

        inputs = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                inputs,
                max_new_tokens=settings.max_new_tokens,
                do_sample=True,
                temperature=0.7,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        prompt_length = inputs.shape[1]
        new_tokens = outputs[0][prompt_length:]
        reply = self.tokenizer.decode(new_tokens, skip_special_tokens=True)

        return reply.strip()
