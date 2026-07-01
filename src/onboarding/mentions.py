"""Parse @mentions from Feishu message events for onboarding auto-fill."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MentionedBot:
    name: str
    open_id: str


@dataclass
class OnboardHints:
    """Values Inspector can infer without asking the user."""

    normal_group: str = ""
    open_id: str = ""
    mention_name: str = ""
    app_id: str = ""
    owner_open_id: str = ""
    owner_name: str = ""

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.normal_group:
            lines.append(f"普通测试群：{self.normal_group}（当前群，自动）")
        if self.open_id:
            src = self.mention_name or "被 @ 的 Bot"
            lines.append(f"open_id：{self.open_id}（来自 @{src}，自动）")
        elif self.mention_name:
            lines.append(f"已 @ {self.mention_name}，但未解析到 open_id")
        if self.app_id:
            lines.append(f"App ID：{self.app_id}（按名称匹配，自动）")
        if self.owner_name or self.owner_open_id:
            who = self.owner_name or self.owner_open_id
            lines.append(f"负责人：{who}（发起人，自动）")
        return lines


def is_inspector_mentioned(
    mentions,
    *,
    inspector_open_id: str = "",
    inspector_names: tuple[str, ...] = (),
) -> bool:
    """True when the Inspector bot itself is @mentioned in a group message."""
    inspector_names_lower = {n.strip().lower() for n in inspector_names if n.strip()}
    for mention in mentions or []:
        id_obj = getattr(mention, "id", None)
        open_id = (getattr(id_obj, "open_id", "") or "").strip() if id_obj else ""
        name = (getattr(mention, "name", "") or "").strip()
        if inspector_open_id and open_id == inspector_open_id:
            return True
        if name.lower() in inspector_names_lower:
            return True
    return False


def parse_message_mentions(
    mentions,
    *,
    inspector_open_id: str = "",
    inspector_names: tuple[str, ...] = (),
) -> list[MentionedBot]:
    """Extract non-Inspector bot mentions from a Feishu im.message.receive_v1 message."""
    inspector_names_lower = {n.strip().lower() for n in inspector_names if n.strip()}
    results: list[MentionedBot] = []
    seen: set[str] = set()

    for mention in mentions or []:
        id_obj = getattr(mention, "id", None)
        open_id = ""
        if id_obj:
            open_id = (getattr(id_obj, "open_id", "") or "").strip()
        name = (getattr(mention, "name", "") or "").strip()
        if not open_id and not name:
            continue
        if inspector_open_id and open_id == inspector_open_id:
            continue
        if name.lower() in inspector_names_lower:
            continue
        key = open_id or name.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(MentionedBot(name=name, open_id=open_id))

    return results


def pick_target_mention(
    mentions: list[MentionedBot],
    bot_name: str,
) -> MentionedBot | None:
    """Choose the mention most likely to be the bot under test."""
    if not mentions:
        return None
    target = bot_name.strip().lower()
    if target:
        for m in mentions:
            if m.name.strip().lower() == target:
                return m
        for m in mentions:
            if target in m.name.strip().lower() or m.name.strip().lower() in target:
                return m
    if len(mentions) == 1:
        return mentions[0]
    return None
