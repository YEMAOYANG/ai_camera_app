from __future__ import annotations

import re
from pathlib import Path

from services.ai_text_provider import AiTextProvider, UnavailableAiTextProvider
from services.conversation_policy_service import ConversationPolicyService
from services.prompt_registry import PromptRegistry
from services.voice_wake_service import clean_camera_command_text


class VoiceConversationService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        ai_text_provider: AiTextProvider | None = None,
        prompt_registry: PromptRegistry | None = None,
    ):
        self.policy_service = ConversationPolicyService(database_url)
        self.ai_text_provider = ai_text_provider or UnavailableAiTextProvider()
        self.prompt_registry = prompt_registry

    def reply(
        self,
        conn,
        *,
        family_id: str,
        device_id: str,
        text: str,
        profile: dict | None = None,
    ) -> dict:
        profile = profile or self.policy_service.build_interaction_profile(
            self.policy_service.get_rules(conn, family_id=family_id)
        )
        evaluation = self.policy_service.evaluate_chat_turn(conn, family_id=family_id)
        if not evaluation["allowed"]:
            return {
                "ok": True,
                "allowed": False,
                "reason": evaluation["reason"],
                "reply": self._blocked_reply(evaluation["reason"], profile),
            }
        command = clean_camera_command_text(text, profile)
        if not command:
            return {
                "ok": True,
                "allowed": False,
                "reason": "empty_command",
                "reply": "我没有听清，你可以再说一次吗？",
            }
        system_prompt = self._system_prompt(profile)
        response = self.ai_text_provider.complete(
            system_prompt=system_prompt,
            user_prompt=command,
            max_tokens=120,
            temperature=0.5,
        )
        raw_reply = response.text.strip() if response and response.text.strip() else self._fallback_reply(profile)
        reply = self._compact_spoken_reply(raw_reply)
        return {
            "ok": True,
            "allowed": True,
            "reason": "reply_generated",
            "reply": reply,
            "command": command,
        }

    def _system_prompt(self, profile: dict) -> str:
        if self.prompt_registry is not None:
            prompt = self.prompt_registry.get_prompt("conversation.child_companion", "v1")
            if prompt is not None:
                body = prompt.body
                return (
                    body.replace("{{wakeName}}", str(profile.get("wakeName") or ""))
                    .replace("{{childNickname}}", str(profile.get("childNickname") or "小朋友"))
                    .replace("{{voiceStyle}}", str(profile.get("voiceStyle") or ""))
                )
        wake_name = str(profile.get("wakeName") or "")
        child = str(profile.get("childNickname") or "小朋友")
        return (
            f"你是家庭摄像头 AI 伙伴，孩子叫你「{wake_name}」。"
            f"请用温柔、短句、适合幼儿园小朋友的中文回复{child}。"
            "每次只说一件事，不要批评，不要制造依赖。"
        )

    def _blocked_reply(self, reason: str, profile: dict) -> str:
        wake_name = str(profile.get("wakeName") or "小暖")
        if reason == "bedtime_quiet":
            return self._wrap_up_text()
        if reason == "single_session_limit_reached":
            return f"{wake_name}今天聊够啦，我们明天再接着聊。"
        if reason == "daily_limit_reached":
            return f"今天和{wake_name}聊得够多啦，先休息一下吧。"
        if reason == "focus_restricted":
            return "专注时间只聊当前这件事，其他我们稍后再说。"
        if reason == "free_chat_disabled":
            return f"{wake_name}在呢，现在先不自由聊天，有事可以直接说。"
        return self._wrap_up_text()

    def _wrap_up_text(self) -> str:
        if self.prompt_registry is not None:
            prompt = self.prompt_registry.get_prompt("conversation.free_chat_wrap_up", "v1")
            if prompt is not None and prompt.body.strip():
                return prompt.body.strip().splitlines()[0]
        return "我也想继续聊，不过现在要保护眼睛啦。我们先去做下一件事，晚点再说。"

    def _fallback_reply(self, profile: dict) -> str:
        wake_name = str(profile.get("wakeName") or "小暖")
        return f"我在呢，{wake_name}听到了。你想聊什么？"

    @staticmethod
    def _compact_spoken_reply(text: str, *, max_chars: int = 120) -> str:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if not value:
            return value
        limit = max(40, int(max_chars))
        if len(value) <= limit:
            return value
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])\s*", value) if item.strip()]
        kept: list[str] = []
        total = 0
        for sentence in sentences:
            next_total = total + len(sentence)
            if kept and next_total > limit:
                break
            if next_total > limit and not kept:
                break
            kept.append(sentence)
            total = next_total
        if kept:
            return "".join(kept).strip()
        return value[:limit].rstrip(" ，,；;：:") + "。"
