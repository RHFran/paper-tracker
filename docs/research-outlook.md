# Six-section reviews and research outlook

[Home](../README.md) · [Agent workflow](agent-workflow.md) · [中文](research-outlook_中文.md)

The research agent reads, interprets and proposes. The program checks the submitted
structure, source anchors and reference numbering, saves the audit, and renders
text/HTML. It does not fill missing sections with a template or replace research
with a hand-written report inside the renderer.

## Each paper: six sections

1. **Problem and design:** the background bottleneck and how the overall design
   addresses it. Separate the authors' stated rationale from an interpretation.
2. **Scientific question:** the question or testable hypothesis.
3. **Method chain:** inputs and data, experimental/model steps, and validation.
4. **Results and highlights:** quantitative results with their units and baselines,
   plus supported contributions. Avoid repeating the same claim as a “highlight.”
5. **Limitations:** specific data, method, evaluation or generalization boundaries.
   A limitation inferred from a narrow dataset must not be attributed to the authors.
6. **Research implications:** useful transferable reasoning or a concrete next
   investigation, phrased as an implication rather than a completed result.

For compatibility the internal `fields` still contains `highlights`, `question`,
`methods` and `findings`. New agent analyses also require `perspective` with
`design_logic`, `limitations` and `inspiration`. Each perspective list has one to
three objects with exactly `text`, `evidence` and `kind` (`reported` or `inferred`).
The program validates every 12–180-character source anchor and marks the distinction
in the report. It merges findings and highlights into the fourth section.

Question and methods must be nonempty, as must either findings or highlights. Do
not invent material to meet this condition. If an abstract cannot support a
substantive review, explain that exclusion in the screening decision. When an
abstract does support a bounded review, retain its actual evidence level.

## Finish the issue with a research argument

The closing section appears **after all paper reviews and before References**.
Its purpose differs from the opening overview: connect what the papers establish,
where they differ and what remains worth testing. Do not concatenate summaries,
force connections between unrelated topics, or infer field-wide consensus from
one issue. Different benchmark percentages are not necessarily comparable.

New schema-2 agent results require an `outlook` object:

- `synthesis`: the same `paragraphs → sentences → {text, citations}` shape as the
  overview. Every citation contains the global `ref` and an exact `evidence`
  anchor. A multi-paper synthesis must cite at least two selected papers across
  its paragraphs. Cite every participating paper in a comparison.
- `open_questions`: one to four cited statements framing concrete unresolved
  questions. Questions can be the agent's inference from the source findings;
  they must not pretend to be author-reported limitations.
- `ideas`: one to four objects with exactly `status: "proposed"`, `title`, `basis`,
  `hypothesis`, `experiment`, `validation`, and `expected_value`. Aim for two to
  four useful ideas when supported, rather than manufacturing a quota.

Each idea's `basis` contains one to three cited statements using the same global
references. Its remaining fields describe a **proposal**:

- State a testable hypothesis or research question.
- Identify feasible data, a baseline, a controlled intervention and an ablation.
- Specify held-out evaluation, useful metrics and a result that would count
  against the hypothesis. Include uncertainty where the scientific question needs it.
- Explain conditionally what a positive or negative result would help decide.

These are original suggestions for the issue, not proof of global scientific
novelty. Do not claim completed experiments or guaranteed gains. Preserve essential
boundaries: source-model emulation is not real-world validation, a climate emulator
is not a language model, and visually convincing synthetic observations need not
preserve scientifically relevant information.

## Validation and durable behavior

The program checks required fields, bounds, language, source anchors, reference
identity, and `proposed` status. It cannot prove entailment, feasibility, scientific
correctness or novelty. Rendering rejects stale reference maps and altered anchors,
escapes HTML, and never calls a model. The structured content remains in the audit.

No selected papers means an empty synthesis, question list and idea list. No
research ideas are invented for an empty issue. Old frozen schema-1 jobs remain
resumable with their earlier result shape; old saved reports and delivery envelopes
are not rewritten by this upgrade. A revised report must follow the explicit
revision/delivery workflow rather than replacing an already claimed envelope.

Offline checks:

```sh
python -m unittest discover -s tests -p test_outlook.py -v
python -m unittest discover -s tests -p test_agent_jobs.py -v
```

These test data are synthetic; passing them is not a live scientific or model
quality evaluation.
