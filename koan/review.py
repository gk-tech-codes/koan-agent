"""Peer Review — GAN-style adversarial code generation.

Two agents: Coder writes, Critic reviews. They iterate until
the Critic approves or max rounds reached.

Enabled with --review flag.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from koan.log import get_logger
from koan.types import ContentBlock, Message, MessageRole, Mode

log = get_logger("review")

DEFAULT_MAX_ROUNDS = 3

CRITIC_SYSTEM_PROMPT = """You are a senior code reviewer. Your job is to critique code written by another agent.

Review for:
- Security vulnerabilities (SQL injection, XSS, missing auth)
- Error handling (missing try/except, unhandled edge cases)
- Performance issues (N+1 queries, unnecessary loops)
- Code quality (naming, structure, readability)
- Missing tests or validation

Be specific. Point to exact issues with line references.

Respond in this format:
VERDICT: APPROVE or REVISE
ISSUES: (list specific issues, empty if approved)
SUGGESTIONS: (optional improvements even if approved)

If the code is good enough, approve it. Don't be unnecessarily strict.
"""

CODER_REVISION_PROMPT = """A code reviewer found issues with your implementation.
Fix ALL the issues listed below, then provide the complete updated implementation.

Reviewer feedback:
{feedback}

Provide the complete fixed implementation.
"""


class PeerReview:
    """Runs adversarial coder-critic loop."""

    def __init__(self, provider: Any, max_rounds: int = DEFAULT_MAX_ROUNDS):
        self._provider = provider
        self._max_rounds = max_rounds

    async def run(
        self,
        user_request: str,
        initial_response: str,
        system_prompt: str,
        on_status: Callable[[str], None] | None = None,
    ) -> dict:
        """Run peer review on an initial response.

        Returns: {
            "final_response": str,
            "rounds": int,
            "approved": bool,
            "review_log": [{"round": N, "verdict": str, "issues": str}]
        }
        """
        current_code = initial_response
        review_log = []

        for round_num in range(1, self._max_rounds + 1):
            if on_status:
                on_status(f"\n\033[33m◆ Review round {round_num}/{self._max_rounds}\033[0m\n")

            # Critic reviews
            if on_status:
                on_status(f"\033[90m  ⊘ Critic reviewing...\033[0m")

            critique = await self._get_critique(user_request, current_code)

            verdict = "REVISE"
            if "VERDICT: APPROVE" in critique or "VERDICT:APPROVE" in critique:
                verdict = "APPROVE"

            review_log.append({
                "round": round_num,
                "verdict": verdict,
                "feedback": critique[:500],
            })

            if on_status:
                icon = "\033[32m✓\033[0m" if verdict == "APPROVE" else "\033[33m⟳\033[0m"
                on_status(f"\r  {icon} Critic: {verdict}\n")

            if verdict == "APPROVE":
                if on_status:
                    on_status(f"\033[32m◆ Approved after {round_num} round(s)\033[0m\n\n")
                return {
                    "final_response": current_code,
                    "rounds": round_num,
                    "approved": True,
                    "review_log": review_log,
                }

            # Coder revises
            if on_status:
                on_status(f"\033[90m  ⟳ Coder revising...\033[0m")

            current_code = await self._get_revision(user_request, current_code, critique)

            if on_status:
                on_status(f"\r  \033[36m✓\033[0m Coder revised\n")

        # Max rounds reached
        if on_status:
            on_status(f"\033[33m◆ Max rounds reached — accepting current version\033[0m\n\n")

        return {
            "final_response": current_code,
            "rounds": self._max_rounds,
            "approved": False,
            "review_log": review_log,
        }

    async def _get_critique(self, user_request: str, code: str) -> str:
        """Ask critic agent to review the code."""
        messages = [
            Message(role=MessageRole.SYSTEM, blocks=[
                ContentBlock(type="text", data={"text": CRITIC_SYSTEM_PROMPT})
            ]),
            Message(role=MessageRole.USER, blocks=[
                ContentBlock(type="text", data={
                    "text": f"Original request: {user_request}\n\nCode to review:\n{code}"
                })
            ]),
        ]

        from koan.types import EventType
        text_parts = []
        async for event in self._provider.stream(messages, []):
            if event.type == EventType.TEXT_DELTA:
                text_parts.append(event.data.get("text", ""))

        return "".join(text_parts)

    async def _get_revision(self, user_request: str, code: str, feedback: str) -> str:
        """Ask coder agent to fix issues found by critic."""
        revision_prompt = CODER_REVISION_PROMPT.format(feedback=feedback)

        messages = [
            Message(role=MessageRole.USER, blocks=[
                ContentBlock(type="text", data={
                    "text": f"Original request: {user_request}\n\nCurrent implementation:\n{code}\n\n{revision_prompt}"
                })
            ]),
        ]

        from koan.types import EventType
        text_parts = []
        async for event in self._provider.stream(messages, []):
            if event.type == EventType.TEXT_DELTA:
                text_parts.append(event.data.get("text", ""))

        return "".join(text_parts)
