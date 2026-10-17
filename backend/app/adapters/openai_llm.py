"""Real OpenAI adapter. Activated only when LLM_PROVIDER=openai and OPENAI_API_KEY are
set. Uses the chat-completions JSON mode over httpx; failures raise LLMError and the
pipeline routes the ticket to needs_review instead of guessing."""
import json
from typing import Any

import httpx

from ..ports import LLMClient, LLMError

_CLASSIFY_SCHEMA = (
    'Return JSON: {"category": one of refund_request|billing_inquiry|bug_report|'
    'account_issue|how_to, "confidence": 0..1, "amount_cents": integer or null}.'
)


class OpenAILLM:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model
        self.name = f"openai:{model}"

    def complete_json(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        if task == "classify":
            prompt = (
                "Classify this customer support ticket. " + _CLASSIFY_SCHEMA +
                "\nSubject: " + payload["subject"] + "\nBody: " + payload["body"]
            )
        elif task == "draft":
            docs = "\n".join(
                f'- "{d["title"]}" ({d["slug"]}): {d["span"]}' for d in payload["retrieved_docs"]
            )
            prompt = (
                "Draft a short support reply grounded ONLY in these policy excerpts. "
                'Return JSON: {"reply_text": string, "citations": [{"doc_slug", "doc_title", '
                '"quote"}] where each quote is copied verbatim from the excerpt, '
                '"grounded": boolean}.\nTicket category: ' + payload["category"] +
                "\nTicket: " + payload["body"] + "\nPolicy excerpts:\n" + (docs or "(none)")
            )
        else:
            raise ValueError(f"unknown task: {task}")

        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as e:
            raise LLMError(f"openai call failed: {e}") from e
        if not isinstance(data, dict):
            raise LLMError("openai returned non-object JSON")
        return data
