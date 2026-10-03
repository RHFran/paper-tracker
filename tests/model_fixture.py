"""Explicit offline model doubles for tests focused on other pipeline contracts."""
import os
from unittest.mock import patch

from literature_digest.analysis import FIELDS, reference_map
from literature_digest.outlook import prepare_outlook


def perspective_fixture(anchor, language="en"):
    zh = language.startswith("zh")
    return {
        "design_logic": [{"text": "合成夹具用受控条件检验玩具系统。" if zh else
                           "The synthetic fixture uses controlled conditions to examine a toy system.",
                           "evidence": anchor, "kind": "reported"}],
        "limitations": [{"text": "该合成结果的推论限于夹具系统。" if zh else
                          "The synthetic inference is limited to the fixture system.",
                          "evidence": anchor, "kind": "inferred"}],
        "inspiration": [{"text": "可检验改变玩具系统输入后结果是否稳定。" if zh else
                         "A proposed test would vary toy inputs to assess result stability.",
                         "evidence": anchor, "kind": "inferred"}]}


def outlook_fixture(citations, language="en"):
    """Synthetic proposal only; production code never supplies canned content."""
    zh = language.startswith("zh")
    def sentence(en, cn):
        return {"text": cn if zh else en, "citations": citations}
    return {"synthesis": {"paragraphs": [{"sentences": [sentence(
                "The synthetic sources describe bounded toy-system experiments.", "合成来源描述受限玩具系统实验。")]}]},
            "open_questions": [sentence("Would the fixture result persist after changing the toy inputs?",
                                         "改变玩具输入后夹具结果是否保持？")],
            "ideas": [{"status": "proposed", "title": "合成输入敏感性检验" if zh else "Synthetic input sensitivity test",
                       "basis": [sentence("The fixture reports a controlled toy study.", "夹具报告受控玩具研究。")],
                       "hypothesis": "改变输入会改变夹具测量。" if zh else "Changing inputs will alter fixture measurements.",
                       "experiment": "对比原始输入和扰动输入的玩具系统重复试验。" if zh else "Repeat the toy test using original and perturbed inputs as comparison groups.",
                       "validation": "若两组结果无法区分则不支持假设。" if zh else "Indistinguishable measurements between groups would fail to support the hypothesis.",
                       "expected_value": "若成立，可帮助确定夹具输入敏感性。" if zh else "If supported, this would characterize fixture input sensitivity."}]}


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
        fields["question"] = list(fields["findings"])
        fields["methods"] = list(fields["findings"])
        return {"mode": "llm_grounded", "model": "offline-fixture", "language": config["language"], "fields": fields,
                "perspective": perspective_fixture(paper.evidence[:120], config["language"])}

    def overview(papers, config, http):
        paragraphs = []
        if papers:
            claim = papers[0].analysis["fields"]["findings"][0]
            paragraphs = [{"sentences": [{"text": claim["text"], "citations": [{"ref": 1, "evidence": claim["evidence"]}]}]}]
        return {"mode": "llm_grounded", "language": config["language"], "paragraphs": paragraphs,
                "references": reference_map(papers), "warnings": []}

    def outlook(papers, config, http):
        from literature_digest.outlook import empty_outlook
        citations = [{"ref": index, "evidence": paper.analysis["fields"]["findings"][0]["evidence"]}
                     for index, paper in enumerate(papers, 1)]
        data = outlook_fixture(citations, config["language"]) if papers else empty_outlook()
        return {**prepare_outlook(data, papers, config["language"]), "mode": "llm_grounded" if papers else "empty"}

    for name, function in (("analyze", analyze), ("compose_overview", overview), ("compose_outlook", outlook)):
        context = patch("literature_digest.pipeline." + name, side_effect=function)
        context.start()
        test.addCleanup(context.stop)
