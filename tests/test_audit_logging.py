import json
import tempfile
import unittest
from pathlib import Path

import app as app_module


class AuditLoggingTestCase(unittest.TestCase):
    def test_append_audit_event_writes_valid_json_with_events_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_path = app_module.AUDIT_LOG_PATH
            try:
                app_module.AUDIT_LOG_PATH = Path(tmp) / "answer_vote_audit.json"

                app_module._append_audit_event(
                    {
                        "event_type": "answer_submitted",
                        "username": "alice",
                        "answer_text": "hello",
                    }
                )
                app_module._append_audit_event(
                    {
                        "event_type": "vote_submitted",
                        "username": "bob",
                        "selected_option_id": "Q0_V1",
                    }
                )

                raw = app_module.AUDIT_LOG_PATH.read_text(encoding="utf-8")
                payload = json.loads(raw)
                self.assertIn("events", payload)
                self.assertEqual(len(payload["events"]), 2)
                self.assertEqual(payload["events"][0]["event_type"], "answer_submitted")
                self.assertEqual(payload["events"][1]["event_type"], "vote_submitted")
            finally:
                app_module.AUDIT_LOG_PATH = original_path


if __name__ == "__main__":
    unittest.main()
