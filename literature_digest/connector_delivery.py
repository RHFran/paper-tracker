"""Immutable transport adapter for actual program-generated digests. No research import."""
from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from .analysis import require_analysis_payload
from .config import valid_email
from .figures import validate_inline_images

from .references import validate_reference_files
from .state import State, state_scope

POLICY = "required-v1"
MAX_INPUT_BYTES = 32 * 1024 * 1024


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _sha(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def validate_inline_references(images, html):
    """Keep every CID image and its HTML reference paired before any delivery."""
    class References(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.content_ids = set()

        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name == "src" and value and value.strip().lower().startswith("cid:"):
                    self.content_ids.add(value.strip()[4:])

    if not isinstance(html, str):
        raise ValueError("Prepared HTML must be a string")
    parser = References()
    parser.feed(html)
    parser.close()
    if parser.content_ids != {item["content_id"] for item in images}:
        raise ValueError("Prepared inline image CID references do not match HTML")
    return images


def read_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("JSON input exceeds the 32 MiB limit")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON keys are not allowed")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON is not allowed")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON input must be valid UTF-8 JSON") from exc


def _object(value, required, optional=(), label="Object"):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(label + " has missing or unknown fields")
    return value


def _text(value, label, maximum=2000, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum or any(ord(c) < 32 and c not in "\n\t\r" for c in value):
        raise ValueError(label + " must be a nonempty bounded string")
    return value.strip()


def _timestamp(value, label):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
        if not parsed or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except ValueError:
        raise ValueError(label + " must be an ISO timestamp with timezone") from None


def _result(item):
    payload = item["payload"]
    return {"status": item["status"], "digest_id": item["id"], "workflow": payload.get("workflow", "program_pipeline_connector"),
            "paper_count": payload["paper_count"], "envelope_sha256": payload["envelope_sha256"],
            "paths": payload["paths"], "automatic_send": False}


def _check_payload(item, config):
    payload = item["payload"]
    if payload.get("analysis_policy") != POLICY or payload.get("transport") != "connector" or payload.get("recipient", "").lower() != config["recipient"].lower():
        raise ValueError("This is not the selected audience's connector outbox")
    from .pipeline import config_fingerprint
    if payload.get("config_fingerprint") != config_fingerprint(config):
        raise ValueError("Prepared connector settings changed; restore the original settings before using this immutable outbox")
    directory = Path(payload["bundle_dir"])
    for name, expected in payload["artifact_sha256"].items():
        if Path(name).name != name:
            raise ValueError("Invalid prepared artifact path")
        path = directory / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Prepared artifact integrity check failed: " + name)
    envelope = read_json(payload["paths"]["envelope"])
    if _sha(_json(envelope)) != payload["envelope_sha256"]:
        raise ValueError("Prepared send envelope integrity check failed")
    validate_reference_files(envelope["attachments"])
    images = validate_inline_images(envelope.get("inline_images", []))
    validate_inline_references(images, envelope["html"])
    if images != validate_inline_images(payload.get("inline_images", [])):
        raise ValueError("Prepared inline image payload integrity check failed")
    if images:
        expected_paths = [str(directory / item["filename"]) for item in images]
        if payload["paths"].get("inline_images") != expected_paths:
            raise ValueError("Prepared inline image paths integrity check failed")
        for image in images:
            if payload["artifact_sha256"].get(image["filename"]) != image["sha256"]:
                raise ValueError("Prepared inline image artifact integrity check failed")
    return envelope


def prepare_payload(config, state, identifier, payload, audit):
    """Freeze only a completed real pipeline result, while its state lock is held."""
    require_analysis_payload(payload)
    if state.get(identifier) or state.open_deliveries():
        raise ValueError("An existing outbox must be reused or reconciled, never replaced")
    references = validate_reference_files(payload.get("reference_files", []))
    images = validate_inline_images(payload.get("inline_images", []))
    validate_inline_references(images, payload["html"])
    envelope = {"schema_version": 1, "digest_id": identifier, "recipient": payload["recipient"],
                "subject": payload["subject"], "text": payload["text"], "html": payload["html"], "attachments": references}
    if images:
        envelope["inline_images"] = images
    envelope_hash = _sha(_json(envelope))
    files = {"digest.txt": payload["text"], "digest.html": payload["html"],
             "audit.json": _json(audit), "envelope.json": _json(envelope)}
    files.update({r["filename"]: r["content"] for r in references})
    for image in images:
        if image["filename"] in files or image["filename"] == "manifest.json":
            raise ValueError("Prepared inline image filename conflicts with another artifact")
        files[image["filename"]] = base64.b64decode(image["content_base64"], validate=True)
    files["manifest.json"] = _json({"digest_id": identifier, "envelope_sha256": envelope_hash,
                                  "files": {name: _sha(body) for name, body in files.items()}})
    directory = Path(config["output_dir"]).resolve() / "connector" / identifier
    directory.parent.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        raise ValueError("An unregistered immutable bundle already exists; reconcile state before continuing")
    temporary = Path(tempfile.mkdtemp(prefix=".prepare-", dir=directory.parent))
    try:
        for name, body in files.items():
            with (temporary / name).open("xb") as handle:
                handle.write(body.encode("utf-8") if isinstance(body, str) else body)
            (temporary / name).chmod(0o600)
        temporary.rename(directory)
    finally:
        if temporary.exists():
            for path in temporary.iterdir():
                path.unlink()
            temporary.rmdir()
    paths = {"text": str(directory / "digest.txt"), "html": str(directory / "digest.html"),
             "audit": str(directory / "audit.json"), "envelope": str(directory / "envelope.json"),
             "manifest": str(directory / "manifest.json")}
    paths.update({r["format"]: str(directory / r["filename"]) for r in references})
    if images:
        paths["inline_images"] = [str(directory / image["filename"]) for image in images]
    frozen = {**payload, "transport": "connector", "language": config["language"],
              "envelope_sha256": envelope_hash, "bundle_dir": str(directory), "paths": paths,
              "paper_count": len(audit["papers"]), "artifact_sha256": {name: _sha(body) for name, body in files.items()}}
    item = state.prepare(identifier, frozen)
    return {**_result(item), "next": "Review authorization, then begin-send before exactly one connected-mail tool call; confirm-sent imports its actual provider receipt."}


def prepared_result(item, config):
    _check_payload(item, config)
    return {**_result(item), "reused_prepared_outbox": True,
            "next": "Use begin-send only for prepared status; reconcile sending/uncertain status with actual provider records. Never automatically resend."}


def begin_send(config, identifier, now=None):
    """One-shot durable claim BEFORE the external connected-mail tool is called."""
    state = State(config["state_path"], scope=state_scope(config))
    try:
        with state.lock():
            item = state.get(identifier)
            if not item or item["status"] != "prepared" or state.unresolved():
                raise ValueError("Only a prepared outbox with no unresolved sends can be claimed. Never automatically resend; inspect provider records.")
            envelope = _check_payload(item, config)
            today = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(config["timezone"])).date().isoformat()
            if item["payload"]["harvest_until"] != today:
                raise ValueError("Prepared outbox is stale; do not send it without reconciling the earlier preparation")
            from .agent_jobs import validate_revision_delivery
            if state.payload_has_sent_aliases(item["payload"]) and not validate_revision_delivery(state, item["payload"]):
                raise ValueError("Outbox contains already-sent papers")
            state.status(identifier, "sending")
            return {**_result(state.get(identifier)), "send_claimed": True,
                    "next": "Call the authorized connected-mail tool exactly once with the immutable envelope; import its actual receipt. Any uncertain result stays pending."}
    finally:
        state.close()


def confirm_sent(config, identifier, receipt):
    """Import the host's actual provider receipt; acceptance is not inbox delivery."""
    state = State(config["state_path"], scope=state_scope(config))
    try:
        with state.lock():
            item = state.get(identifier)
            if not item or item["payload"].get("analysis_policy") != POLICY or item["payload"].get("transport") != "connector":
                raise ValueError("Connector outbox was not found for this audience")
            _object(receipt, {"digest_id", "envelope_sha256", "provider", "status", "sender", "recipient"},
                    {"message_id", "thread_id", "accepted_at", "provider_receipt"}, "Provider receipt")
            if not valid_email(receipt["recipient"]):
                raise ValueError("Receipt recipient must be one email address")
            if receipt["digest_id"] != identifier or receipt["envelope_sha256"] != item["payload"]["envelope_sha256"] or receipt["recipient"].lower() != config["recipient"].lower():
                raise ValueError("Receipt does not match the prepared digest, audience and envelope hash")
            if not valid_email(receipt["sender"]) or not valid_email(receipt["recipient"]):
                raise ValueError("Receipt sender and recipient must be single email addresses")
            _text(receipt["provider"], "receipt.provider", 200)
            if receipt["status"] not in ("accepted", "uncertain", "pending", "rejected"):
                raise ValueError("Receipt status must be accepted, uncertain, pending or rejected")
            if item["status"] == "sent":
                if state.receipt(identifier) != receipt:
                    raise ValueError("A different receipt is already recorded for this immutable digest")
                return {**_result(item), "receipt_recorded": True, "already_confirmed": True, "delivery_guaranteed": False}
            if item["status"] not in ("sending", "uncertain"):
                raise ValueError("Claim the prepared envelope with begin-send before the external send")
            # Preserve unresolved state for queued, failed and malformed acceptance
            # results. An import must never turn uncertainty into a resend opportunity.
            if receipt["status"] != "accepted" or not isinstance(receipt.get("message_id"), str) or not receipt["message_id"].strip() or not receipt.get("accepted_at") or not receipt.get("provider_receipt"):
                state.record_receipt(identifier, receipt)
                state.status(identifier, "uncertain")
                return {**_result(state.get(identifier)), "receipt_recorded": True,
                        "next": "Provider acceptance is unconfirmed. Check actual provider records; do not resend."}
            _text(receipt["message_id"], "receipt.message_id", 1000)
            _timestamp(receipt["accepted_at"], "receipt.accepted_at")
            if not isinstance(receipt["provider_receipt"], dict):
                raise ValueError("provider_receipt must be the actual provider response object")
            def response_strings(value):
                if isinstance(value, dict):
                    return [s for v in value.values() for s in response_strings(v)]
                if isinstance(value, list):
                    return [s for v in value for s in response_strings(v)]
                return [value] if isinstance(value, str) else []
            if receipt["message_id"] not in response_strings(receipt["provider_receipt"]):
                raise ValueError("Provider receipt does not contain the claimed message identifier")
            # Receipt/state commit is atomic; snapshot artifact integrity is checked
            # before send, but missing local files must not erase real acceptance.
            state.mark_sent(identifier, receipt=receipt)
            return {**_result(state.get(identifier)), "receipt_recorded": True,
                    "provider_message_id": receipt["message_id"], "delivery_guaranteed": False}
    finally:
        state.close()
