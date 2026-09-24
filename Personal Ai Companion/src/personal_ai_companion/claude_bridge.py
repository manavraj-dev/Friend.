from __future__ import annotations

import os
from typing import Any


class ClaudeBridge:
    """Thin wrapper around Anthropic/Gemini-compatible providers. Safe to import without a configured API key."""

    def __init__(self, api_key: str | None = None, provider: str = "anthropic"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.provider = (provider or "anthropic").lower()
        if self.provider == "gemini" and not self.api_key:
            self.api_key = os.getenv("GEMINI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, *, system_prompt: str, user_message: str, context: str = "") -> str:
        if not self.is_available():
            return self._fallback_reply(user_message, context)

        if self.provider == "gemini":
            return self._generate_gemini(system_prompt, user_message, context)
        return self._generate_anthropic(system_prompt, user_message, context)

    def _generate_anthropic(self, system_prompt: str, user_message: str, context: str = "") -> str:
        try:
            import anthropic
        except Exception:
            return self._fallback_reply(user_message, context)

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": f"{context}\n\n{user_message}"}],
            )
            text = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    text += getattr(block, "text", "")
            return text.strip() or self._fallback_reply(user_message, context)
        except Exception:
            return self._fallback_reply(user_message, context)

    def _generate_gemini(self, system_prompt: str, user_message: str, context: str = "") -> str:
        try:
            import google.generativeai as genai
        except Exception:
            return self._fallback_reply(user_message, context)

        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(model_name="gemini-1.5-flash")
            prompt = f"{system_prompt}\n\n{context}\n\n{user_message}"
            response = model.generate_content(prompt)
            text = ""
            if hasattr(response, "text"):
                text = response.text
            elif hasattr(response, "candidates"):
                for candidate in response.candidates:
                    if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                        for part in candidate.content.parts:
                            text += getattr(part, "text", "")
            return text.strip() or self._fallback_reply(user_message, context)
        except Exception:
            return self._fallback_reply(user_message, context)

    @staticmethod
    def _fallback_reply(user_message: str, context: str = "") -> str:
        message = user_message.strip()
        if not message:
            return "I’m ready to help. Add your API key in the UI and choose Anthropic or Gemini to enable model replies."
        return (
            "I’ve logged this turn and am keeping the memory flow local-first. "
            "Add your API key in the UI and choose a provider like Anthropic or Gemini for live model replies. "
            f"Current context: {context[:180] or 'general conversation'}. "
            f"Your message was: \"{message[:200]}\""
        )
