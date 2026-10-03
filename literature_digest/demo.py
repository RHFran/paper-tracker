"""Deterministic, entirely offline examples, never records of actual research.

This module deliberately does not import the live pipeline: demo generation must
not initialize a delivery database, provider client, model, or mail transport.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path

from .analysis import is_chinese, output_language, reference_map, validate_analysis, validate_overview
from .models import Paper
from .render import render
from .references import reference_files, reference_manifest


_SOURCES = (
    {
        "id": "forest-bvoc",
        "title": ("Drought intensity and species-specific canopy volatile emissions",
                  "干旱强度与树种特异性的冠层挥发物排放"),
        "track": "bvoc",
        "claims": {
            "highlights": [("The synthetic design evaluates species-specific emission responses instead of assuming a uniform drought effect.",
                            "该合成设计分别检验树种特异性的排放响应，而不预设所有树种具有一致的干旱效应。",
                            "The synthetic design evaluates species-specific emission responses rather than assuming a uniform drought effect.")],
            "question": [("This synthetic study asks how drought intensity changes volatile emissions across tree species.",
                          "该合成研究考察不同干旱强度如何改变不同树种的挥发物排放。",
                          "We ask how drought intensity changes volatile emissions across tree species.")],
            "methods": [("Repeated branch-chamber sampling and gas chromatography were analyzed with species-by-treatment mixed-effects models.",
                         "研究采用重复枝条气室采样与气相色谱测量，并以树种与处理的交互项建立混合效应模型。",
                         "Repeated branch-chamber sampling and gas chromatography were analyzed using species-by-treatment mixed-effects models."),
                        ("The simulated experiment followed 72 saplings from three tree species through two controlled drought cycles.",
                         "模拟实验对三个树种的72株幼树实施两个受控干旱周期并进行跟踪测量。",
                         "The simulated experiment followed 72 saplings from three tree species through two controlled drought cycles."),
                        ("Interpretation is limited to controlled sapling experiments; mature forests and seasonal field variation were not tested.",
                         "研究范围限于受控幼树实验；成熟森林与野外季节变化未接受检验。",
                         "The controlled sapling experiment did not test mature forests or seasonal variation under field conditions.")],
            "findings": [("In the simulated observations, moderate drought increased isoprene emissions in one species but not the other two.",
                          "模拟观测中，中度干旱提高了一个树种的异戊二烯排放，而另两个树种未出现这一变化。",
                          "Moderate drought increased isoprene emissions in one species but not the other two in the simulated observations."),
                         ("Severe drought reduced emissions in all three simulated species relative to their watered controls.",
                          "相对于各自的正常供水对照，三个模拟树种在重度干旱下的排放均降低。",
                          "Severe drought reduced emissions in all three simulated species relative to their watered controls.")],
        },
    },
    {
        "id": "canopy-species",
        "title": ("Seasonal spectral and structural observations for tree-species mapping",
                  "结合季节光谱与结构观测进行树种制图"),
        "track": "tree_species",
        "claims": {
            "highlights": [("The synthetic mapping workflow integrates seasonal spectral and canopy-height observations for tree-species discrimination.",
                            "该合成制图流程融合季节光谱与冠层高度观测，用于区分树种。",
                            "The synthetic mapping workflow integrates seasonal spectral and canopy-height observations for tree-species discrimination.")],
            "question": [("This synthetic study asks whether seasonal spectral and canopy-height information improve tree-species discrimination.",
                          "该合成研究检验季节光谱与冠层高度信息能否改善树种区分。",
                          "We ask whether seasonal spectral and canopy-height information improve tree-species discrimination.")],
            "methods": [("The simulated workflow combines two-season hyperspectral imagery with lidar height features in a random-forest classifier.",
                         "模拟流程在随机森林分类器中融合两个季节的高光谱影像与激光雷达高度特征。",
                         "A random-forest classifier combined two-season hyperspectral imagery with lidar canopy-height features."),
                        ("The simulated dataset contains 120 plots covering four tree species; training and evaluation use spatially separate stands.",
                         "模拟数据集含覆盖四个树种的120个样地，训练与评估采用空间分离的林分。",
                         "The synthetic dataset contains 120 four-species plots; training and evaluation use spatially separate stands."),
                        ("The simulated comparison covers one site; transfer to other forests, sensors, and rare species remains untested.",
                         "模拟比较仅覆盖一个地点，跨森林、跨传感器及稀有树种的迁移能力尚未接受检验。",
                         "The comparison covers one simulated site; transfer to other forests, sensors, and rare species remains untested.")],
            "findings": [("In the simulated held-out stands, spectral-plus-height features achieve macro-F1 0.82 versus 0.74 for the single-season spectral baseline.",
                          "在模拟的留出林分中，光谱与高度融合的宏平均F1为0.82，单季光谱基线为0.74。",
                          "Simulated held-out macro-F1 was 0.82 for spectral-plus-height features and 0.74 for the single-season spectral baseline.")],
        },
    },
)


def _papers(language):
    zh = is_chinese(language)
    papers = []
    for fixture in _SOURCES:
        evidence = "DEMO / SYNTHETIC SOURCE. All studies, authors, observations, and results below are invented for an offline layout preview.\n\n"
        evidence += "\n".join(item[2] for items in fixture["claims"].values() for item in items)
        fields = {key: [{"text": item[1 if zh else 0], "evidence": item[2]} for item in items]
                  for key, items in fixture["claims"].items()}
        paper = Paper(
            title="[DEMO / SYNTHETIC" + (" 合成示例] " if zh else "] ") + fixture["title"][1 if zh else 0],
            source_id=fixture["id"], source="demo",
            url="https://example.org/demo/" + fixture["id"],
            authors=["A. Example（模拟作者）", "B. Example（模拟作者）"] if zh else
                    ["A. Example (simulated author)", "B. Example (simulated author)"],
            journal="DEMO 合成研究示例（非真实期刊）" if zh else "DEMO Synthetic Research (not a real journal)",
            publication_date="2026-10-01",
            publication_date_label="固定示例日期；非发表记录" if zh else "Fixed fixture date; not a publication record",
            kind="合成演示文献；非真实发表、非同行评审" if zh else "Synthetic demo; not published or peer reviewed",
            abstract=evidence, full_text=evidence,
            evidence_level="本地合成证据示例；非真实论文正文" if zh else "Locally authored synthetic evidence; not a real paper",
            tracks=[fixture["track"]],
            provenance=[{"source": "demo", "synthetic": True, "retrieved": False,
                         "identifier": "demo:" + fixture["id"],
                         "note": "Authored offline fixture; example.org links are placeholders, not research sources."}],
            warnings=["DEMO：所有数据与结果均为虚构，仅用于预览。" if zh else
                      "DEMO: all data and findings are invented, solely for preview."],
        )
        paper.analysis = {"mode": "synthetic_demo", "synthetic": True, "language": language,
                          "fields": validate_analysis(fields, evidence, language),
                          "notice": "合成示例分析；未调用模型；逐条锚点可在示例源文中核对。" if zh else
                                    "Synthetic example analysis; no model called; anchors refer only to the fixture source."}
        papers.append(paper)
    return papers


def _overview(papers, language):
    zh = is_chinese(language)

    def citation(ref, field, index=0):
        return {"ref": ref, "evidence": papers[ref - 1].analysis["fields"][field][index]["evidence"]}

    sentences = [
        {"text": "这组合成研究从树种间的挥发物排放差异与冠层观测的树种区分两个角度，讨论森林中的树种差异。" if zh else
                 "These synthetic studies examine differences among forest tree species through volatile-emission responses and discrimination from canopy observations.",
         "citations": [citation(1, "question"), citation(2, "question")]},
        {"text": "在受控幼树实验的模拟观测中，中度干旱仅提高了一个树种的异戊二烯排放，显示这一响应在三个模拟树种间并不一致。" if zh else
                 "In the simulated sapling observations, moderate drought increases isoprene emissions in only one of three species, illustrating a species-dependent response within this experiment.",
         "citations": [citation(1, "findings")]},
        {"text": "在树种制图的模拟留出林分中，光谱与高度融合取得0.82的宏平均F1，高于单季光谱基线的0.74。" if zh else
                 "For the simulated mapping task, spectral-plus-height features achieve held-out macro-F1 of 0.82 compared with 0.74 for the single-season spectral baseline.",
         "citations": [citation(2, "findings")]},
        {"text": "两项示例的适用范围分别受限于受控幼树实验和单地点分类比较，尚不能据此推断成熟森林或跨地点的表现。" if zh else
                 "The examples remain bounded by a controlled sapling experiment and a single-site classification comparison, leaving mature-forest responses and cross-site performance unresolved.",
         "citations": [citation(1, "methods", 2), citation(2, "methods", 2)]},
    ]
    return {"mode": "synthetic_demo", "synthetic": True, "language": language,
            "paragraphs": validate_overview({"paragraphs": [{"sentences": sentences}]}, papers, language),
            "references": reference_map(papers), "warnings": [],
            "notice": "DEMO / synthetic, hand-authored offline introduction; no model or real literature used."}


def _atomic_write(path, content):
    """Use a unique sibling temporary file, without importing the live pipeline."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix="." + path.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content.encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def preview(config, language=None):
    """Write an offline zh/en preview without touching state, network, or mail.

    Dates and findings are fixed synthetic fixtures so repeated calls with the
    same options produce identical files. User topics are replaced only in the
    private rendering copy by this example's two ecological research topics.
    """
    selected = output_language(config) if language is None else language
    if (not isinstance(selected, str)
            or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", selected)
            or not (is_chinese(selected) or selected.lower().split("-")[0] == "en")):
        raise ValueError("Offline demo supports Chinese (zh-CN) or English (en) language tags")
    zh = is_chinese(selected)
    options = copy.deepcopy(config)
    options["language"] = selected
    options["topics"] = [
        {"id": "bvoc", "name": "森林挥发物与干旱响应" if zh else "Forest volatiles and drought responses"},
        {"id": "tree_species", "name": "遥感树种识别" if zh else "Remote-sensing tree-species mapping"},
    ]
    # The preview never renders user-supplied external figure URLs or data URIs.
    options["images"] = {"mode": "off", "max_per_paper": 0}
    options["llm"] = {"enabled": False}
    options["mail"] = {"enabled": False}
    notice = ("DEMO / 合成示例：所有论文、作者、期刊、日期、数据与研究结果均为虚构；未检索来源、未调用模型、未发送邮件、未更改投递状态。" if zh else
              "DEMO / SYNTHETIC: all papers, authors, journals, dates, data, and findings are invented. No sources queried, model called, mail sent, or delivery state changed.")
    meta = {"demo": True, "synthetic": True, "demo_notice": notice,
            "title": "DEMO / 合成科研文献预览" if zh else "DEMO / Synthetic research digest preview",
            "local_date": "2026-10-03", "timezone": config.get("timezone", "UTC"),
            "language": selected, "publication_window_days": 7,
            "window_start": "2026-09-26 (fixed synthetic fixture)",
            "window_end": "2026-10-03 (fixed synthetic fixture)",
            "date_precision_note": "Fixed invented dates; no real publication eligibility was assessed.",
            "retrieval_mode": "offline_synthetic_fixture", "retrieved": 0,
            "fixture_count": 2, "relevant": 2, "already_sent": 0,
            "date_unknown": 0, "outside_window": 0, "deferred": 0,
            "sources": [], "errors": [], "failure": False}
    papers = _papers(selected)
    overview = _overview(papers, selected)
    references = reference_files(papers, "demo." + selected)
    meta["reference_exports"] = reference_manifest(references)
    text, html = render(papers, meta, options, overview)
    audit = {"meta": meta, "overview": overview,
             "papers": [paper.export(include_text=True) for paper in papers], "excluded": []}
    output = Path(config.get("output_dir", "output"))
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for extension, body in (("html", html), ("txt", text),
                            ("json", json.dumps(audit, ensure_ascii=False, indent=2) + "\n")):
        path = output / ("demo." + selected + "." + extension)
        _atomic_write(path, body)
        paths[extension] = str(path)
    for item in references:
        path = output / item["filename"]
        _atomic_write(path, item["content"])
        paths[item["format"]] = str(path)
    return {"status": "demo_preview", "synthetic": True, "language": selected,
            "paper_count": len(papers), "paths": paths,
            "notice": notice, "network_used": False, "state_changed": False, "mail_sent": False}
