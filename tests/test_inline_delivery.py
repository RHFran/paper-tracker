"""Offline inline-image delivery contracts; no SMTP or source network access."""
import base64
import copy
import hashlib
import json
import os
import tempfile
import struct
import zlib
import unittest
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

from literature_digest.analysis import ANALYSIS_POLICY
from literature_digest.config import DEFAULTS
from literature_digest.connector_delivery import (
    MAX_INPUT_BYTES, _check_payload, begin_send, prepare_payload,
    prepared_result, read_json, validate_inline_references,
)
from literature_digest.mail import MailSetupError, send_smtp
from literature_digest.models import Paper
from literature_digest.pipeline import config_fingerprint
from literature_digest.references import reference_files
from literature_digest.state import State, state_scope
from model_fixture import enable_model


# Valid 1x1 PNGs, generated only as synthetic transport fixtures.
def png_fixture(number=1):
    def chunk(kind, content):
        return (struct.pack(">I", len(content)) + kind + content +
                struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes((0, number, 0, 0, 255)))) + chunk(b"IEND", b""))


PNG = png_fixture()
NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def inline_fixture(number=1):
    raw = png_fixture(number)
    digest = hashlib.sha256(raw).hexdigest()
    return {"filename": f"figure-{digest}.png", "content_type": "image/png",
            "content_base64": base64.b64encode(raw).decode("ascii"),
            "content_id": f"figure-{digest}@super-paper-radar", "sha256": digest,
            "size_bytes": len(raw)}


CID = inline_fixture()["content_id"]


class InlineDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = copy.deepcopy(DEFAULTS)
        self.config.update(timezone="UTC", language="en",
                           state_path=str(Path(self.tmp.name) / "state.db"),
                           output_dir=str(Path(self.tmp.name) / "out"))
        self.config["mail"]["enabled"] = True
        enable_model(self, self.config)
        environment = patch.dict(os.environ, {
            "LITERATURE_SMTP_HOST": "smtp.example.test", "LITERATURE_SMTP_USER": "fixture",
            "LITERATURE_SMTP_PASSWORD": "synthetic-test-only", "LITERATURE_MAIL_FROM": "sender@example.org",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.state = State(self.config["state_path"], state_scope(self.config))
        self.addCleanup(self.state.close)
        paper = Paper("Synthetic figure fixture", "fixture", "test", "https://example.org/fixture")
        self.payload = {"recipient": self.config["recipient"], "subject": "Synthetic inline figure test",
                        "text": "Synthetic figure source: https://example.org/fixture",
                        "html": f'<p>Synthetic figure</p><img src="cid:{CID}" alt="Fixture">',
                        "harvest_until": NOW.date().isoformat(), "aliases": ["test:fixture"],
                        "analysis_policy": ANALYSIS_POLICY, "config_fingerprint": config_fingerprint(self.config),
                        "reference_files": reference_files([paper], "fixture-references"),
                        "inline_images": [inline_fixture()]}
        self.audit = {"papers": [{"title": paper.title}]}

    def prepare(self):
        with self.state.lock():
            return prepare_payload(self.config, self.state, "fixture", self.payload, self.audit)

    def send(self):
        messages = []

        class FakeSMTP:
            def __init__(self, *args, **kwargs): pass
            def login(self, *args): pass
            def send_message(self, message, **kwargs):
                # Exercise actual wire serialization and MIME decoding as well.
                messages.append(BytesParser(policy=policy.default).parsebytes(message.as_bytes()))
                return {}
            def quit(self): pass

        self.state.prepare("fixture", self.payload)
        self.assertTrue(send_smtp(self.payload, self.config, self.state, "fixture", smtp_ssl=FakeSMTP, now=NOW))
        return messages[0]

    def assert_rejected_before_smtp(self):
        self.state.prepare("fixture", self.payload)
        with self.assertRaises(MailSetupError):
            send_smtp(self.payload, self.config, self.state, "fixture",
                      smtp_ssl=lambda *a, **kw: self.fail("SMTP was attempted"), now=NOW)
        self.assertEqual(self.state.get("fixture")["status"], "prepared")

    def test_smtp_keeps_inline_images_related_to_html_and_citations_regular(self):
        self.payload["inline_images"].append(inline_fixture(2))
        self.payload["html"] += f'<img src="cid:{inline_fixture(2)["content_id"]}" alt="Second fixture">'
        message = self.send()
        self.assertEqual(message.get_content_type(), "multipart/mixed")
        alternative, ris, bib = list(message.iter_parts())
        self.assertEqual(alternative.get_content_type(), "multipart/alternative")
        plain, related = list(alternative.iter_parts())
        self.assertEqual(plain.get_content_type(), "text/plain")
        self.assertEqual(related.get_content_type(), "multipart/related")
        html, *images = list(related.iter_parts())
        self.assertEqual(html.get_content_type(), "text/html")
        self.assertIn(f'src="cid:{CID}"', html.get_content())
        for actual, expected in zip(images, self.payload["inline_images"], strict=True):
            self.assertEqual(actual.get_content_type(), expected["content_type"])
            self.assertEqual(actual["Content-ID"], "<" + expected["content_id"] + ">")
            self.assertEqual(actual.get_content_disposition(), "inline")
            self.assertEqual(actual.get_filename(), expected["filename"])
            self.assertEqual(actual.get_payload(decode=True), base64.b64decode(expected["content_base64"]))
        for actual, expected in zip((ris, bib), self.payload["reference_files"], strict=True):
            self.assertEqual(actual.get_content_disposition(), "attachment")
            self.assertEqual(actual.get_filename(), expected["filename"])
            self.assertEqual(actual.get_payload(decode=True), expected["content"].encode("utf-8"))
        self.assertEqual(self.state.get("fixture")["status"], "sent")

    def test_smtp_without_citations_does_not_make_images_regular_attachments(self):
        self.payload["reference_files"] = []
        message = self.send()
        self.assertEqual(message.get_content_type(), "multipart/alternative")
        self.assertEqual(list(message.iter_parts())[1].get_content_type(), "multipart/related")
        self.assertEqual(list(message.iter_attachments()), [])

    def test_smtp_without_images_retains_previous_structure(self):
        del self.payload["inline_images"]
        self.payload["html"] = "<p>Synthetic digest</p>"
        message = self.send()
        alternative = list(message.iter_parts())[0]
        self.assertEqual([part.get_content_type() for part in alternative.iter_parts()], ["text/plain", "text/html"])
        self.assertEqual(len(list(message.iter_attachments())), 2)

    def test_invalid_inline_assets_stop_before_smtp(self):
        original = copy.deepcopy(self.payload)
        for field, value in (("sha256", "0" * 64), ("size_bytes", len(PNG) + 1),
                             ("content_base64", "not valid base64!"), ("content_type", "text/html"),
                             ("filename", "../figure.png"), ("content_id", "<header-injection>")):
            with self.subTest(field=field):
                self.payload = copy.deepcopy(original)
                self.payload["inline_images"][0][field] = value
                self.assert_rejected_before_smtp()

    def test_cid_mismatch_and_unreferenced_image_stop_before_smtp(self):
        for html in ('<img src="cid:missing@paper-radar">', "<p>No figure reference</p>"):
            with self.subTest(html=html):
                self.payload["html"] = html
                self.assert_rejected_before_smtp()

    def test_missing_inline_images_stop_before_smtp(self):
        self.payload["inline_images"] = []
        self.assert_rejected_before_smtp()

    def test_html_cid_check_accepts_repeats_entities_and_self_closing_tags(self):
        images = [inline_fixture()]
        html = (f'<img src="cid:{CID.replace(chr(64), "&#64;")}" />'
                f'<img src="CID:{CID}">'
                '<!-- <img src="cid:ignored"> -->')
        self.assertIs(validate_inline_references(images, html), images)

    def test_connector_freezes_binary_images_hashes_and_paths_without_mutation(self):
        original = copy.deepcopy(self.payload)
        result = self.prepare()
        self.assertEqual(self.payload, original)
        envelope_path = Path(result["paths"]["envelope"])
        envelope_bytes = envelope_path.read_bytes()
        envelope = read_json(envelope_path)
        self.assertEqual(envelope["inline_images"], original["inline_images"])
        self.assertEqual(envelope["attachments"], original["reference_files"])
        self.assertEqual(len(result["paths"]["inline_images"]), 1)
        image_path = Path(result["paths"]["inline_images"][0])
        self.assertEqual(image_path.name, inline_fixture()["filename"])
        self.assertEqual(image_path.read_bytes(), PNG)
        manifest = read_json(result["paths"]["manifest"])
        self.assertEqual(manifest["files"][image_path.name], original["inline_images"][0]["sha256"])
        stored = self.state.get("fixture")
        self.assertEqual(stored["payload"]["artifact_sha256"][image_path.name], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(_check_payload(stored, self.config), envelope)
        # Caller-owned dictionaries cannot rewrite the on-disk immutable snapshot.
        self.payload["inline_images"][0]["content_base64"] = "mutated"
        self.assertTrue(prepared_result(stored, self.config)["reused_prepared_outbox"])
        self.assertEqual(envelope_path.read_bytes(), envelope_bytes)
        claim = begin_send(self.config, "fixture", now=NOW)
        self.assertTrue(claim["send_claimed"])
        self.assertEqual(envelope_path.read_bytes(), envelope_bytes)

    def test_connector_without_images_preserves_old_envelope_shape(self):
        del self.payload["inline_images"]
        self.payload["html"] = "<p>Synthetic digest</p>"
        result = self.prepare()
        envelope = read_json(result["paths"]["envelope"])
        self.assertNotIn("inline_images", envelope)
        self.assertNotIn("inline_images", result["paths"])
        self.assertTrue(begin_send(self.config, "fixture", now=NOW)["send_claimed"])

    def test_connector_tampered_binary_blocks_claim(self):
        result = self.prepare()
        Path(result["paths"]["inline_images"][0]).write_bytes(PNG + b"tampered")
        with self.assertRaisesRegex(ValueError, "integrity"):
            begin_send(self.config, "fixture", now=NOW)
        self.assertEqual(self.state.get("fixture")["status"], "prepared")

    def test_connector_tampered_envelope_blocks_claim(self):
        result = self.prepare()
        path = Path(result["paths"]["envelope"])
        envelope = read_json(path)
        envelope["inline_images"][0]["content_base64"] = "tampered"
        path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity"):
            begin_send(self.config, "fixture", now=NOW)
        self.assertEqual(self.state.get("fixture")["status"], "prepared")

    def test_connector_tampered_payload_or_missing_artifact_registration_fails(self):
        self.prepare()
        original = self.state.get("fixture")
        for kind in ("image", "paths", "hash", "omitted"):
            with self.subTest(kind=kind):
                item = copy.deepcopy(original)
                if kind == "image":
                    item["payload"]["inline_images"][0]["sha256"] = "0" * 64
                elif kind == "paths":
                    item["payload"]["paths"]["inline_images"] = []
                elif kind == "hash":
                    del item["payload"]["artifact_sha256"][inline_fixture()["filename"]]
                else:
                    del item["payload"]["inline_images"]
                with self.assertRaises(ValueError):
                    _check_payload(item, self.config)

    def test_prepare_rejects_invalid_assets_or_cids_without_outbox(self):
        self.payload["html"] = '<img src="cid:unknown">'
        with self.assertRaisesRegex(ValueError, "CID"):
            self.prepare()
        self.assertIsNone(self.state.get("fixture"))
        self.assertFalse(Path(self.config["output_dir"]).exists())
        self.payload["html"] = f'<img src="cid:{CID}">'
        self.payload["inline_images"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertIsNone(self.state.get("fixture"))
        self.assertFalse(Path(self.config["output_dir"]).exists())

    def test_read_json_is_bounded_but_allows_image_sized_envelopes(self):
        self.assertGreaterEqual(MAX_INPUT_BYTES, 24 * 1024 * 1024)
        path = Path(self.tmp.name) / "oversize.json"
        with path.open("wb") as handle:
            handle.truncate(MAX_INPUT_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "limit"):
            read_json(path)
        path.write_text('{"fixture": true, "fixture": false}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            read_json(path)


if __name__ == "__main__":
    unittest.main()
