# Digest editorial outline

This is a human-readable design guide, not a runtime template or configuration
file. The renderer produces both a plain-text and an HTML version.

1. **Title and reporting window**: profile, language, local date, sources and
   retrieval status.
2. **Research overview**: source-grounded themes across the selected papers,
   with global numbered references. Distinguish observations from interpretation.
3. **Topic sections**: each paper has exactly four interpretation blocks:
   **Highlights**, **Scientific question**, **Experimental or modeling methods**,
   and **Main results** (核心亮点、科学问题、实验或模型方法、主要结果). Fold relevant
   data details and reported bounds into methods/results instead of adding
   separate data or limitations blocks. Show the evidence level (metadata,
   abstract or retrieved full text), original link and publication date.
4. **Source figures, when eligible**: retain the original caption, attribution,
   license and link. If reuse rights cannot be established, link to the source.
   Never invent a research figure or depict a model-generated image as evidence.
5. **References**: one global number per unique paper, reused across topics.
6. **Coverage and audit**: source failures, exclusions, truncation and missing
   evidence are recorded in the accompanying JSON report.

“Nature-style” means a concise editorial structure and global numerical
references. This project is not affiliated with Nature and does not promise
publisher-exact typesetting or the editorial review of a journal.
