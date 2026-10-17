"""Deterministic, key-free LLM. Wraps the rules classifier and composes a grounded
reply template from retrieved docs. This is what CI and offline dev run on; the
OpenAI adapter implements the same interface for real generation."""
from typing import Any

from ..classifier import classify, extract_amount_cents
from ..ports import LLMClient


class StubLLM:
    name = "stub-rules-v1"

    def complete_json(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        if task == "classify":
            cat, conf = classify(payload["subject"] + "\n" + payload["body"])
            return {"category": cat, "confidence": conf,
                    "amount_cents": extract_amount_cents(payload["body"])}
        if task == "draft":
            return self._draft(payload)
        raise ValueError(f"unknown task: {task}")

    @staticmethod
    def _verbatim_excerpt(body: str, max_chars: int = 260) -> str:
        """A quote that is guaranteed to be a verbatim span of the doc - groundedness
        is enforced downstream, so the stub cites real text, not a headline rendering."""
        body = body.strip()
        if len(body) <= max_chars:
            return body
        cut = body[:max_chars]
        # end on a sentence boundary when one exists inside the window
        last = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        if last > max_chars // 2:
            return cut[: last + 1]
        return cut.rsplit(" ", 1)[0]

    def _draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        category = payload["category"]
        docs = payload["retrieved_docs"]
        citations = []
        lines = []
        for top in docs[:2]:
            quote = self._verbatim_excerpt(top["body"])
            citations.append({"doc_slug": top["slug"], "doc_title": top["title"],
                              "quote": quote})
            lines.append(f'According to our policy "{top["title"]}": {quote}')
        openers = {
            "refund_request": "Thanks for flagging this - I can help with the refund.",
            "billing_inquiry": "Happy to clear up this billing question.",
            "bug_report": "Thanks for the detailed report - sorry you hit this.",
            "account_issue": "Let's get your account sorted out.",
            "how_to": "Great question - here's how that works.",
        }
        body = "\n\n".join([
            "Hi there,",
            openers.get(category, "Thanks for reaching out."),
            *lines,
            "If anything above doesn't match what you're seeing, reply here and a human "
            "teammate will pick it up.",
            "Best,\nResolveDesk Support",
        ])
        grounded = bool(citations)
        return {"reply_text": body, "citations": citations, "grounded": grounded}
