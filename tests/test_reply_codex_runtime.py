from src.models import ReplyInfo
from src.reply_wait import is_completion_reply, pick_final_replies

CARD = (
    '{"body":{"elements":['
    '{"content":"群聊正常","element_id":"_2","tag":"markdown"},'
    '{"element_id":"_3","tag":"hr"},'
    '{"content":"gpt-demo · out 7 · in 16.6k cw 0 cr 3.5k · ctx 6%\\n~/workspace/agent-runtime",'
    '"element_id":"_4","tag":"markdown"}'
    "]}}"
)


def test_runtime_footer_card_counts_as_completion():
    reply = ReplyInfo(msg_type="interactive", content=CARD)
    assert is_completion_reply(reply)
    assert pick_final_replies([reply])
