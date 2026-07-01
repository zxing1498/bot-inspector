"""Feishu Open API client for Inspector bot."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from src.models import ReplyInfo
from src.reply_wait import is_completion_reply
from src.assertions import is_feishu_card_content_stripped

FEISHU_BASE = "https://open.feishu.cn/open-apis"


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, timeout: float = 30.0):
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout = timeout
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._bot_open_id_cache: dict[str, str] = {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
    ) -> dict[str, Any]:
        url = f"{FEISHU_BASE}{path}"
        headers = {"Authorization": f"Bearer {self.get_tenant_access_token()}"}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
                files=files,
                data=data,
            )
            try:
                payload = resp.json()
            except Exception:
                payload = {}
            if resp.status_code >= 400:
                detail = payload.get("msg") or resp.text[:300]
                raise RuntimeError(
                    f"Feishu HTTP {resp.status_code}: {detail} (url={path})"
                )
            if payload.get("code", 0) != 0:
                raise RuntimeError(
                    f"Feishu API error {payload.get('code')}: {payload.get('msg')}"
                )
            return payload

    def get_tenant_access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", 0) != 0:
                raise RuntimeError(f"Token error: {data.get('msg')}")
            self._token = data["tenant_access_token"]
            self._token_expires_at = time.time() + data.get("expire", 7200)
            return self._token

    def validate_token(self) -> bool:
        try:
            self.get_tenant_access_token()
            return True
        except Exception:
            return False

    def list_chat_members(
        self, chat_id: str, *, member_id_type: str = "open_id"
    ) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"member_id_type": member_id_type, "page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", f"/im/v1/chats/{chat_id}/members", params=params)
            members.extend(data.get("data", {}).get("items", []))
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token", "")
        return members

    def is_bot_in_chat(
        self,
        chat_id: str,
        target_app_id: str,
        *,
        target_open_id: str = "",
        bot_name: str = "",
    ) -> bool:
        """Check if target bot is in chat. member_id_type=app_id is unsupported; use open_id scan."""
        if target_open_id:
            try:
                members = self.list_chat_members(chat_id)
                if any(m.get("member_id") == target_open_id for m in members):
                    return True
            except Exception:
                pass
        if bot_name:
            open_id = self._resolve_open_id_from_mentions(chat_id, bot_name)
            if open_id:
                return True
        try:
            data = self._request(
                "GET",
                f"/im/v1/chats/{chat_id}",
                params={"user_id_type": "open_id"},
            )
            # If chat exists and bot was recently active, mentions scan is the reliable signal.
            return bool(data.get("data"))
        except Exception:
            return False

    def send_interactive(self, receive_id: str, card: dict[str, Any]) -> dict[str, Any]:
        body = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        return self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body=body,
        )

    def send_text(
        self,
        receive_id: str,
        text: str,
        *,
        receive_id_type: str = "chat_id",
        reply_in_thread: bool = False,
        root_id: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        if reply_in_thread:
            body["reply_in_thread"] = True
        if root_id:
            body["root_id"] = root_id
        return self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json_body=body,
        )

    def _resolve_open_id_from_mentions(self, chat_id: str, bot_name: str) -> str:
        """Fallback: extract bot open_id from recent @mentions in chat history."""
        try:
            messages = self.list_messages(chat_id, page_size=50)
        except Exception:
            return ""
        for msg in messages:
            for mention in msg.get("mentions") or []:
                if mention.get("name") == bot_name and mention.get("id", "").startswith("ou_"):
                    return mention["id"]
        return ""

    def resolve_bot_open_id(
        self,
        app_id: str,
        *,
        bot_name: str = "",
        chat_id: str = "",
        configured_open_id: str = "",
    ) -> str:
        """Get bot open_id for @mention. Feishu requires ou_xxx, not cli_xxx app_id."""
        if configured_open_id:
            self._bot_open_id_cache[app_id] = configured_open_id
            return configured_open_id
        if app_id in self._bot_open_id_cache:
            return self._bot_open_id_cache[app_id]
        if app_id == self.app_id:
            try:
                data = self._request("GET", "/bot/v3/info")
                open_id = data.get("bot", {}).get("open_id", "")
                if open_id:
                    self._bot_open_id_cache[app_id] = open_id
                    return open_id
            except Exception:
                pass
        if chat_id and bot_name:
            open_id = self._resolve_open_id_from_mentions(chat_id, bot_name)
            if open_id:
                self._bot_open_id_cache[app_id] = open_id
                return open_id
        return ""

    def send_text_with_at(
        self,
        chat_id: str,
        text: str,
        target_app_id: str,
        *,
        target_name: str = "bot",
        target_open_id: str = "",
        reply_in_thread: bool = False,
    ) -> dict[str, Any]:
        """Send text message with @bot using open_id (Feishu does not accept app_id in at tag)."""
        open_id = target_open_id or self.resolve_bot_open_id(
            target_app_id,
            bot_name=target_name,
            chat_id=chat_id,
        )
        if not open_id:
            raise RuntimeError(
                f"无法 @ Bot「{target_name}」：缺少 open_id。"
                f"请在 config/bots.yaml 配置 open_id，或先在群里手动 @ 该 Bot 一次。"
            )
        at_text = f'<at user_id="{open_id}">{target_name}</at> {text}'
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": at_text}, ensure_ascii=False),
        }
        if reply_in_thread:
            body["reply_in_thread"] = True
        return self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body=body,
        )

    def reply_text_with_at(
        self,
        reply_to_message_id: str,
        text: str,
        target_app_id: str,
        *,
        target_name: str = "bot",
        target_open_id: str = "",
    ) -> dict[str, Any]:
        """Reply to a message (e.g. file) with @bot — binds file context for the target bot."""
        open_id = target_open_id or self.resolve_bot_open_id(
            target_app_id,
            bot_name=target_name,
        )
        if not open_id:
            raise RuntimeError(
                f"无法 @ Bot「{target_name}」：缺少 open_id。"
                f"请在 config/bots.yaml 配置 open_id，或先在群里手动 @ 该 Bot 一次。"
            )
        at_text = f'<at user_id="{open_id}">{target_name}</at> {text}'
        body = {
            "msg_type": "text",
            "content": json.dumps({"text": at_text}, ensure_ascii=False),
        }
        return self._request(
            "POST",
            f"/im/v1/messages/{reply_to_message_id}/reply",
            json_body=body,
        )

    def send_post_with_at(
        self,
        chat_id: str,
        text: str,
        target_app_id: str,
        *,
        target_name: str = "bot",
        target_open_id: str = "",
        reply_in_thread: bool = False,
    ) -> dict[str, Any]:
        open_id = target_open_id or self.resolve_bot_open_id(
            target_app_id,
            bot_name=target_name,
            chat_id=chat_id,
        )
        if not open_id:
            raise RuntimeError(
                f"无法 @ Bot「{target_name}」：缺少 open_id。"
                f"请在 config/bots.yaml 配置 open_id，或先在群里手动 @ 该 Bot 一次。"
            )
        content = {
            "zh_cn": {
                "content": [
                    [
                        {"tag": "at", "user_id": open_id, "user_name": target_name},
                        {"tag": "text", "text": f" {text}"},
                    ]
                ]
            }
        }
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "post",
            "content": json.dumps(content, ensure_ascii=False),
        }
        if reply_in_thread:
            body["reply_in_thread"] = True
        return self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body=body,
        )

    def upload_file(self, file_path: Path) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{FEISHU_BASE}/im/v1/files",
                headers={"Authorization": f"Bearer {self.get_tenant_access_token()}"},
                data={"file_type": "stream", "file_name": file_path.name},
                files={"file": (file_path.name, file_path.read_bytes())},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", 0) != 0:
                raise RuntimeError(f"Upload failed: {data.get('msg')}")
            return data["data"]["file_key"]

    def send_file_message(
        self,
        chat_id: str,
        file_key: str,
        *,
        reply_in_thread: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
        }
        if reply_in_thread:
            body["reply_in_thread"] = True
        return self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body=body,
        )

    def upload_image(self, file_path: Path) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{FEISHU_BASE}/im/v1/images",
                headers={"Authorization": f"Bearer {self.get_tenant_access_token()}"},
                data={"image_type": "message"},
                files={"image": (file_path.name, file_path.read_bytes())},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", 0) != 0:
                raise RuntimeError(f"Image upload failed: {data.get('msg')}")
            return data["data"]["image_key"]

    def send_image_message(
        self,
        chat_id: str,
        image_key: str,
        *,
        reply_in_thread: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
        }
        if reply_in_thread:
            body["reply_in_thread"] = True
        return self._request(
            "POST",
            "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json_body=body,
        )

    def list_messages(
        self,
        container_id: str,
        *,
        container_id_type: str = "chat",
        start_time: str | None = None,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "container_id_type": container_id_type,
            "container_id": container_id,
            "page_size": page_size,
            "sort_type": "ByCreateTimeDesc",
        }
        if start_time:
            params["start_time"] = start_time
        params["card_msg_content_type"] = "user_card_content"
        data = self._request("GET", "/im/v1/messages", params=params)
        return data.get("data", {}).get("items", [])

    def list_thread_messages(
        self,
        thread_id: str,
        *,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """List messages inside a topic thread (omt_*). API does not support start_time."""
        return self.list_messages(
            thread_id,
            container_id_type="thread",
            page_size=page_size,
        )

    def resolve_thread_id(self, thread_or_message_id: str) -> str:
        """Return omt_* thread id from thread id or root message id (om_*)."""
        token = (thread_or_message_id or "").strip()
        if not token:
            return ""
        if token.startswith("omt_"):
            return token
        if token.startswith("om_"):
            try:
                msg = self.get_message(token)
            except Exception:
                msg = None
            if msg:
                return (msg.get("thread_id") or "").strip()
        return ""

    def _gather_bot_message_candidates(
        self,
        chat_id: str,
        *,
        after_ts: float,
        start_time: str,
        thread_hint: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Merge chat-level and thread-level messages for reply polling."""
        by_id: dict[str, dict[str, Any]] = {}
        for msg in self.list_messages(chat_id, start_time=start_time):
            mid = msg.get("message_id", "")
            if mid:
                by_id[mid] = msg

        thread_ids: set[str] = set()
        resolved = self.resolve_thread_id(thread_hint)
        if resolved:
            thread_ids.add(resolved)

        for msg in list(by_id.values()):
            tid = (msg.get("thread_id") or "").strip()
            if not tid:
                continue
            create_time = int(msg.get("create_time", "0")) / 1000
            if create_time >= after_ts:
                thread_ids.add(tid)

        for tid in thread_ids:
            for msg in self.list_thread_messages(tid):
                create_time = int(msg.get("create_time", "0")) / 1000
                if create_time < after_ts:
                    continue
                mid = msg.get("message_id", "")
                if mid:
                    by_id[mid] = msg
        return by_id

    def get_message(
        self,
        message_id: str,
        *,
        user_card_content: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch a single message; user_card_content returns the sender's original card JSON."""
        params: dict[str, Any] = {}
        if user_card_content:
            params["card_msg_content_type"] = "user_card_content"
        data = self._request(
            "GET",
            f"/im/v1/messages/{message_id}",
            params=params or None,
        )
        items = data.get("data", {}).get("items", [])
        return items[0] if items else None

    def list_message_reactions(
        self,
        message_id: str,
        *,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """List emoji reactions on a message (GET /im/v1/messages/:message_id/reactions)."""
        if not (message_id or "").startswith("om_"):
            return []
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/im/v1/messages/{message_id}/reactions",
                params=params,
            )
            batch = data.get("data", {}).get("items", [])
            if isinstance(batch, list):
                items.extend(batch)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token", "")
            if not page_token:
                break
        return items

    def _reaction_from_target_bot(
        self,
        reaction: dict[str, Any],
        *,
        after_ts: float,
        sender_app_id: str | None = None,
        sender_open_id: str | None = None,
    ) -> bool:
        operator = reaction.get("operator") or {}
        op_type = operator.get("operator_type", "")
        op_id = operator.get("operator_id", "")
        allowed_app = {x for x in (sender_app_id,) if x}
        allowed_user = {x for x in (sender_open_id,) if x}
        if op_type == "app":
            if allowed_app and op_id not in allowed_app:
                return False
        elif op_type == "user":
            if allowed_user and op_id not in allowed_user:
                return False
        elif allowed_app or allowed_user:
            return False
        try:
            action_ts = int(reaction.get("action_time", "0")) / 1000
        except (TypeError, ValueError):
            return False
        return action_ts >= after_ts - 0.5

    def reaction_to_reply_info(
        self, reaction: dict[str, Any], after_ts: float
    ) -> ReplyInfo:
        reaction_type = reaction.get("reaction_type") or {}
        emoji_type = ""
        if isinstance(reaction_type, dict):
            emoji_type = str(reaction_type.get("emoji_type", "")).strip()
        try:
            action_ts = int(reaction.get("action_time", "0")) / 1000
        except (TypeError, ValueError):
            action_ts = after_ts
        label = emoji_type or "emoji"
        return ReplyInfo(
            message_id=str(reaction.get("reaction_id", "")),
            msg_type="reaction",
            content=f"表情回复:{label}",
            raw=reaction,
            latency_sec=max(0.0, action_ts - after_ts),
        )

    def collect_bot_reactions(
        self,
        probe_message_ids: list[str],
        *,
        after_ts: float,
        sender_app_id: str | None = None,
        sender_open_id: str | None = None,
    ) -> list[ReplyInfo]:
        """One-shot fetch of target-bot emoji reactions on probe messages."""
        by_id: dict[str, ReplyInfo] = {}
        for message_id in probe_message_ids:
            if not (message_id or "").startswith("om_"):
                continue
            try:
                reactions = self.list_message_reactions(message_id)
            except Exception:
                continue
            for reaction in reactions:
                if not self._reaction_from_target_bot(
                    reaction,
                    after_ts=after_ts,
                    sender_app_id=sender_app_id,
                    sender_open_id=sender_open_id,
                ):
                    continue
                info = self.reaction_to_reply_info(reaction, after_ts)
                rid = info.message_id or str(reaction)
                by_id[rid] = info
        return sorted(by_id.values(), key=lambda r: r.latency_sec)

    def wait_for_any_bot_ack(
        self,
        chat_id: str,
        *,
        after_ts: float,
        timeout_sec: float = 30.0,
        min_count: int = 1,
        poll_interval: float = 1.5,
        sender_app_id: str | None = None,
        sender_open_id: str | None = None,
        thread_id: str = "",
        probe_message_ids: list[str] | None = None,
    ) -> list[ReplyInfo]:
        """Poll bot messages and emoji reactions on probe messages; return earliest acks."""
        deadline = time.time() + timeout_sec
        start_time = str(int(after_ts))
        message_by_id: dict[str, dict[str, Any]] = {}
        reaction_by_id: dict[str, ReplyInfo] = {}
        probe_ids = [m for m in (probe_message_ids or []) if (m or "").startswith("om_")]

        while time.time() < deadline:
            by_id = self._gather_bot_message_candidates(
                chat_id,
                after_ts=after_ts,
                start_time=start_time,
                thread_hint=thread_id,
            )
            for msg in by_id.values():
                sender = msg.get("sender", {})
                if sender.get("sender_type") != "app":
                    continue
                sid = sender.get("id", "")
                allowed = {x for x in (sender_app_id, sender_open_id) if x}
                if allowed and sid not in allowed:
                    continue
                mid = msg.get("message_id", "")
                if mid:
                    message_by_id[mid] = msg

            for message_id in probe_ids:
                try:
                    reactions = self.list_message_reactions(message_id)
                except Exception:
                    continue
                for reaction in reactions:
                    if not self._reaction_from_target_bot(
                        reaction,
                        after_ts=after_ts,
                        sender_app_id=sender_app_id,
                        sender_open_id=sender_open_id,
                    ):
                        continue
                    info = self.reaction_to_reply_info(reaction, after_ts)
                    rid = info.message_id or str(reaction)
                    reaction_by_id[rid] = info

            if len(message_by_id) + len(reaction_by_id) >= min_count:
                break
            time.sleep(poll_interval)

        infos: list[ReplyInfo] = []
        for msg in message_by_id.values():
            info = self.parse_message_content(msg)
            create_time = int(msg.get("create_time", "0")) / 1000
            info.latency_sec = max(0.0, create_time - after_ts)
            infos.append(info)
        infos.extend(reaction_by_id.values())
        infos.sort(key=lambda r: r.latency_sec)
        return infos

    def wait_for_replies(
        self,
        chat_id: str,
        *,
        after_ts: float,
        timeout_sec: float = 30.0,
        min_count: int = 1,
        poll_interval: float = 1.5,
        sender_app_id: str | None = None,
        sender_open_id: str | None = None,
        thread_id: str = "",
    ) -> list[dict[str, Any]]:
        deadline = time.time() + timeout_sec
        start_time = str(int(after_ts))
        collected: list[dict[str, Any]] = []

        while time.time() < deadline:
            by_id = self._gather_bot_message_candidates(
                chat_id,
                after_ts=after_ts,
                start_time=start_time,
                thread_hint=thread_id,
            )
            for msg in by_id.values():
                sender = msg.get("sender", {})
                if sender.get("sender_type") != "app":
                    continue
                sid = sender.get("id", "")
                allowed = {x for x in (sender_app_id, sender_open_id) if x}
                if allowed and sid not in allowed:
                    continue
                if msg not in collected:
                    collected.append(msg)
            if len(collected) >= min_count:
                break
            time.sleep(poll_interval)

        return collected

    def wait_for_completion_replies(
        self,
        chat_id: str,
        *,
        after_ts: float,
        timeout_sec: float = 600.0,
        poll_interval: float = 2.0,
        sender_app_id: str | None = None,
        sender_open_id: str | None = None,
        cancel_check: Callable[[], bool] | None = None,
        thread_id: str = "",
    ) -> tuple[list[dict[str, Any]], bool]:
        """Poll until a final/completion reply or timeout. Returns (raw_messages, completed)."""
        deadline = time.time() + timeout_sec
        start_time = str(int(after_ts))
        by_id: dict[str, dict[str, Any]] = {}

        while time.time() < deadline:
            if cancel_check and cancel_check():
                return list(by_id.values()), False

            candidates = self._gather_bot_message_candidates(
                chat_id,
                after_ts=after_ts,
                start_time=start_time,
                thread_hint=thread_id,
            )
            for msg in candidates.values():
                sender = msg.get("sender", {})
                if sender.get("sender_type") != "app":
                    continue
                sid = sender.get("id", "")
                allowed = {x for x in (sender_app_id, sender_open_id) if x}
                if allowed and sid not in allowed:
                    continue
                mid = msg.get("message_id", "")
                if mid:
                    by_id[mid] = msg

            if by_id:
                collected = list(by_id.values())
                parsed = [self.parse_message_content(m) for m in collected]
                if any(is_completion_reply(p) for p in parsed):
                    return collected, True

            time.sleep(poll_interval)
            if cancel_check and cancel_check():
                return list(by_id.values()), False

        return list(by_id.values()), False

    def send_report_file(self, chat_id: str, report_path: Path) -> None:
        """Upload a report file and send it as a file message."""
        file_key = self.upload_file(report_path)
        self.send_file_message(chat_id, file_key)

    def parse_message_content(self, msg: dict[str, Any]) -> ReplyInfo:
        msg_type = msg.get("msg_type", "text")
        body = msg.get("body", {})
        content_raw = body.get("content", "{}")
        try:
            content_json = json.loads(content_raw)
        except json.JSONDecodeError:
            content_json = {"text": content_raw}

        text = ""
        if msg_type == "text":
            text = content_json.get("text", "")
        elif msg_type == "post":
            text = content_raw
        elif msg_type == "interactive":
            text = content_raw
            message_id = msg.get("message_id", "")
            if message_id and is_feishu_card_content_stripped(text):
                try:
                    full = self.get_message(message_id)
                    if full:
                        full_body = full.get("body", {})
                        text = full_body.get("content", text) or text
                except Exception:
                    pass
        elif msg_type in ("file", "image"):
            text = content_raw
        else:
            text = str(content_json)

        return ReplyInfo(
            message_id=msg.get("message_id", ""),
            msg_type=msg_type,
            content=text,
            raw=msg,
            thread_id=msg.get("thread_id", ""),
            root_id=msg.get("root_id", ""),
        )

    def get_bot_info(self) -> dict[str, Any]:
        data = self._request("GET", "/bot/v3/info")
        return data.get("bot", {})

    def find_app_id_by_name(self, app_name: str) -> str:
        """Match tenant installed app by display name. Requires admin:app.info:readonly."""
        target = app_name.strip().lower()
        if not target:
            return ""
        page_token = ""
        while True:
            params: dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            try:
                data = self._request("GET", "/application/v6/applications", params=params)
            except Exception:
                return ""
            for app in data.get("data", {}).get("app_list", []):
                name = (app.get("app_name") or "").strip().lower()
                if name == target or target in name or name in target:
                    return app.get("app_id", "")
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token", "")
        return ""

    def get_user_name(self, open_id: str, *, chat_id: str = "") -> str:
        if not open_id:
            return ""
        try:
            data = self._request(
                "GET",
                f"/contact/v3/users/{open_id}",
                params={"user_id_type": "open_id"},
            )
            user = data.get("data", {}).get("user", {})
            name = user.get("name") or user.get("en_name") or ""
            if name:
                return name
        except Exception:
            pass

        if chat_id:
            try:
                for member in self.list_chat_members(chat_id):
                    member_id = member.get("member_id", "")
                    if member_id == open_id:
                        name = member.get("name", "")
                        if name:
                            return name
            except Exception:
                pass
        return ""

    def create_topic_test_group(
        self,
        name: str,
        *,
        operator_open_id: str = "",
        target_app_id: str = "",
    ) -> str:
        """Create a thread/topic group and invite operator + target bot. Returns chat_id."""
        body: dict[str, Any] = {
            "name": name[:60],
            "group_message_type": "thread",
            "chat_mode": "group",
            "chat_type": "private",
            "membership_approval": "no_approval_required",
        }
        users: list[str] = []
        if operator_open_id:
            users.append(operator_open_id)
        if users:
            body["user_id_list"] = users
        bots: list[str] = []
        if target_app_id and target_app_id != self.app_id:
            bots.append(target_app_id)
        if bots:
            body["bot_id_list"] = bots
        data = self._request(
            "POST",
            "/im/v1/chats",
            params={"user_id_type": "open_id"},
            json_body=body,
        )
        chat_id = data.get("data", {}).get("chat_id", "")
        if not chat_id:
            raise RuntimeError("创建话题群失败：未返回 chat_id")
        return chat_id

    def send_notification(self, chat_id: str, text: str) -> None:
        if chat_id:
            self.send_text(chat_id, text)
