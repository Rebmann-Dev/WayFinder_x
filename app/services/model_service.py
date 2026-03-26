import logging
import os
from threading import Thread
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

from core.config import settings

log = logging.getLogger("wayfinder.model")


class ModelService:
    MAX_INPUT_TOKENS = 4096

    def __init__(self) -> None:
        self.device = self._select_device()
        if self.device.type == "cuda":
            dtype = torch.float16
        elif self.device.type == "mps":
            dtype = torch.float32
        else:
            dtype = torch.float32
        log.info("Loading model %s on %s (%s)", settings.model_name, self.device, dtype)
        self.tokenizer = AutoTokenizer.from_pretrained(settings.model_name)

        load_kwargs: dict[str, Any] = {"dtype": dtype}
        if self.device.type == "mps":
            load_kwargs["attn_implementation"] = "eager"

        self.model = AutoModelForCausalLM.from_pretrained(
            settings.model_name,
            **load_kwargs,
        ).to(self.device)
        self.model.eval()
        log.info("Model ready on %s", self.device)

    @property
    def _uses_manual_mps_decode(self) -> bool:
        return self.device.type == "mps"

    @staticmethod
    def _select_device() -> torch.device:
        forced = os.getenv("WAYFINDER_DEVICE", "").strip()
        if forced:
            return torch.device(forced)
        if torch.cuda.is_available():
            return torch.device("cuda")
        if os.getenv("WAYFINDER_NO_MPS", "").lower() in ("1", "true", "yes"):
            return torch.device("cpu")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    def _prepare_attention_mask(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None,
    ) -> torch.Tensor:
        if attention_mask is not None:
            return attention_mask
        return torch.ones_like(input_ids, device=input_ids.device)

    def _sample_next_token(
        self,
        logits: torch.Tensor,
        *,
        do_sample: bool,
        temperature: float,
    ) -> torch.Tensor:
        logits = logits.float()

        if not do_sample:
            return torch.argmax(logits, dim=-1, keepdim=True)

        safe_temperature = max(temperature, 1e-5)
        normalized = (logits / safe_temperature).cpu()
        normalized = normalized - normalized.max(dim=-1, keepdim=True).values
        probs = torch.softmax(normalized, dim=-1)
        probs = torch.nan_to_num(probs, nan=0.0, posinf=0.0, neginf=0.0)
        probs_sum = probs.sum(dim=-1, keepdim=True)
        if torch.any(probs_sum <= 0):
            return torch.argmax(logits, dim=-1, keepdim=True)
        probs = probs / probs_sum
        return torch.multinomial(probs, num_samples=1).to(logits.device)

    def _stream_manual_decode(
        self,
        *,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None,
        max_new_tokens: int,
        do_sample: bool,
        temperature: float,
    ):
        attention_mask = self._prepare_attention_mask(input_ids, attention_mask)
        current_input_ids = input_ids
        current_attention_mask = attention_mask
        past_key_values = None
        eos_token_id = self.tokenizer.eos_token_id

        for _ in range(max_new_tokens):
            with torch.no_grad():
                outputs = self.model(
                    input_ids=current_input_ids,
                    attention_mask=current_attention_mask,
                    past_key_values=past_key_values,
                    use_cache=True,
                )

            past_key_values = outputs.past_key_values
            next_token = self._sample_next_token(
                outputs.logits[:, -1, :],
                do_sample=do_sample,
                temperature=temperature,
            )

            if eos_token_id is not None and next_token[0, 0].item() == eos_token_id:
                break

            piece = self.tokenizer.decode(
                next_token[0],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            if piece:
                yield piece

            current_input_ids = next_token
            next_attention = torch.ones(
                (current_attention_mask.shape[0], 1),
                dtype=current_attention_mask.dtype,
                device=current_attention_mask.device,
            )
            current_attention_mask = torch.cat(
                [current_attention_mask, next_attention],
                dim=1,
            )

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
            truncation=True,
            max_length=self.MAX_INPUT_TOKENS,
        ).to(self.device)
        log.debug("Agent input tokens: %d", inputs["input_ids"].shape[1])

        if self._uses_manual_mps_decode:
            yield from self._stream_manual_decode(
                input_ids=inputs["input_ids"],
                attention_mask=inputs.get("attention_mask"),
                max_new_tokens=settings.agent_max_new_tokens,
                do_sample=True,
                temperature=settings.agent_temperature,
            )
            return

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
        input_ids = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.device)

        if self._uses_manual_mps_decode:
            yield from self._stream_manual_decode(
                input_ids=input_ids,
                attention_mask=None,
                max_new_tokens=settings.max_new_tokens,
                do_sample=True,
                temperature=0.7,
            )
            return

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        generation_kwargs = {
            "input_ids": input_ids,
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

        input_ids = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.device)

        if self._uses_manual_mps_decode:
            pieces = list(
                self._stream_manual_decode(
                    input_ids=input_ids,
                    attention_mask=None,
                    max_new_tokens=settings.max_new_tokens,
                    do_sample=True,
                    temperature=0.7,
                )
            )
            return "".join(pieces).strip()

        with torch.no_grad():
            outputs = self.model.generate(
                input_ids,
                max_new_tokens=settings.max_new_tokens,
                do_sample=True,
                temperature=0.7,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        prompt_length = input_ids.shape[1]
        new_tokens = outputs[0][prompt_length:]
        reply = self.tokenizer.decode(new_tokens, skip_special_tokens=True)

        return reply.strip()
