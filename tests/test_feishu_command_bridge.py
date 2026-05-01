import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "rdk_x5_demo" / "notebook_vlm_service"
sys.path.insert(0, str(NOTEBOOK))

from feishu_command_bridge import BridgeConfig, parse_event, parse_text_content, should_trigger_patrol


class FeishuCommandBridgeTests(unittest.TestCase):
    def test_parse_text_content_removes_mention_key(self) -> None:
        content = '{"text":"@_user_1 patrol-now"}'
        mentions = [{"key": "@_user_1"}]
        self.assertEqual(parse_text_content(content, mentions), "patrol-now")

    def test_parse_event_extracts_text_and_chat(self) -> None:
        payload = {
            "header": {"event_type": "im.message.receive_v1", "event_id": "evt_1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_sender"}},
                "message": {
                    "message_id": "om_1",
                    "chat_id": "oc_target",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": '{"text":"@_user_1 patrol-now"}',
                    "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}],
                },
            },
        }
        event = parse_event(payload)
        self.assertIsNotNone(event)
        self.assertEqual(event["chat_id"], "oc_target")
        self.assertEqual(event["content_text"], "patrol-now")
        self.assertEqual(event["sender_open_id"], "ou_sender")

    def test_should_trigger_patrol_matches_target_group_and_bot(self) -> None:
        cfg = BridgeConfig(
            host="0.0.0.0",
            port=19100,
            verification_token="",
            target_chat_id="oc_target",
            bot_open_id="ou_bot",
            trigger_texts=frozenset({"patrol-now", "巡视一下"}),
            ssh_path="ssh",
            ssh_user="sunrise",
            ssh_host="172.30.148.147",
            ssh_identity_file="",
            ssh_options=("-o BatchMode=yes",),
            remote_command="bash ~/.local/bin/openclaw-patrol-now",
            log_path=ROOT / "tmp_feishu_bridge.log",
            dedup_ttl_seconds=600,
        )
        event = {
            "event_type": "im.message.receive_v1",
            "chat_id": "oc_target",
            "message_type": "text",
            "content_text": "patrol-now",
            "mentions": [{"id": {"open_id": "ou_bot"}}],
        }
        self.assertTrue(should_trigger_patrol(event, cfg))

    def test_should_trigger_patrol_ignores_other_group(self) -> None:
        cfg = BridgeConfig(
            host="0.0.0.0",
            port=19100,
            verification_token="",
            target_chat_id="oc_target",
            bot_open_id="ou_bot",
            trigger_texts=frozenset({"patrol-now"}),
            ssh_path="ssh",
            ssh_user="sunrise",
            ssh_host="172.30.148.147",
            ssh_identity_file="",
            ssh_options=("-o BatchMode=yes",),
            remote_command="bash ~/.local/bin/openclaw-patrol-now",
            log_path=ROOT / "tmp_feishu_bridge.log",
            dedup_ttl_seconds=600,
        )
        event = {
            "event_type": "im.message.receive_v1",
            "chat_id": "oc_other",
            "message_type": "text",
            "content_text": "patrol-now",
            "mentions": [{"id": {"open_id": "ou_bot"}}],
        }
        self.assertFalse(should_trigger_patrol(event, cfg))


if __name__ == "__main__":
    unittest.main()
