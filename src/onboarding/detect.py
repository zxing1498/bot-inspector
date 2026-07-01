"""Build onboarding auto-fill hints from chat context."""

from __future__ import annotations

from src.feishu.client import FeishuClient
from src.onboarding.mentions import MentionedBot, OnboardHints, pick_target_mention


def build_onboard_hints(
    client: FeishuClient,
    *,
    chat_id: str,
    bot_name: str,
    operator_open_id: str,
    mentioned_bots: list[MentionedBot],
    inspector_open_id: str = "",
    inspector_names: tuple[str, ...] = (),
) -> OnboardHints:
    hints = OnboardHints(
        normal_group=chat_id,
        owner_open_id=operator_open_id,
    )

    if operator_open_id:
        hints.owner_name = client.get_user_name(operator_open_id)

    target = pick_target_mention(mentioned_bots, bot_name)
    if target:
        hints.mention_name = target.name
        hints.open_id = target.open_id

    # App ID cannot come from @mention; try tenant app list by bot / mention name.
    for candidate in (bot_name, hints.mention_name):
        if not candidate:
            continue
        app_id = client.find_app_id_by_name(candidate)
        if app_id and app_id != client.app_id:
            hints.app_id = app_id
            break

    return hints
