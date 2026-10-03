"""Explicit offline model doubles for tests focused on other pipeline contracts."""
import os
from unittest.mock import patch

from literature_digest.analysis import FIELDS, reference_map


def enable_model(test, config):
    config["llm"]["enabled"] = True
    environment = {config["llm"]["base_url_env"]: "https://model.example.org/v1",
                   config["llm"]["api_key_env"]: "synthetic-test-only",
                   config["llm"]["model_env"]: "offline-fixture"}
    context = patch.dict(os.environ, environment)
    context.start()
    test.addCleanup(context.stop)


def install_model_double(test, config):
    enable_model(test, config)

    def analyze(paper, config, http):
        fields = {key: [] for key in FIELDS}
        fields["findings"] = [{"text": "离线模型夹具返回合成来源说明。" if config["language"].startswith("zh") else "The offline fixture describes its synthetic source.",
                               "evidence": paper.evidence[:120]}]
        return {"mode": "llm_grounded", "model": "offline-fixture", "language": config["language"], "fields": fields}

    def overview(papers, config, http):
        paragraphs = []
        if papers:
            claim = papers[0].analysis["fields"]["findings"][0]
            paragraphs = [{"sentences": [{"text": claim["text"], "citations": [{"ref": 1, "evidence": claim["evidence"]}]}]}]
        return {"mode": "llm_grounded", "language": config["language"], "paragraphs": paragraphs,
                "references": reference_map(papers), "warnings": []}

    for name, function in (("analyze", analyze), ("compose_overview", overview)):
        context = patch("literature_digest.pipeline." + name, side_effect=function)
        context.start()
        test.addCleanup(context.stop)
