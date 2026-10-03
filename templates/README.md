# Templates

- `profiles.example.json`: a complete, safe two-reader configuration, using
  reserved `example.org` addresses and disabled sending/model calls. Copy it to
  your private configuration and replace the topics, addresses and schedule.
- [`../config.calendar.example.json`](../config.calendar.example.json): a complete,
  safe three-profile topic calendar for one inbox. It combines Monday BVOCs,
  Wednesday tree-species remote sensing and one specific urban-forest date, with
  different local times. Sending and model calls are disabled. Use `weekdays` for
  recurring days or `dates` for one-off local dates, never both in one schedule
  object; update the example date before use. See the
  [calendar guide](../docs/user-guide.md#different-topics-on-different-days) or
  [中文说明](../docs/user-guide_中文.md#topic-calendar-zh).
- `figures.fragment.json`: merge these root fields into your existing config to
  supply source-figure metadata. Replace the placeholder key with a paper key or
  alias from the JSON audit, and replace the example.org URL with the verified
  source page. Empty rights/asset fields deliberately prevent embedding.
- `digest-outline.md`: the intended report structure and editorial rules; it is
  a design reference, not a file the program loads.

Configuration paths are relative to the JSON file. In a `profiles` configuration,
state and output paths gain a profile-ID directory automatically. For example,
`state/digest.sqlite3` becomes `state/climate-en/digest.sqlite3` for `climate-en`.
An operator shares retrieval and SMTP settings across these profiles. Root `llm`
settings are defaults: a profile may override provider/model/key environment
references to use a different model. Store environment variable names in JSON,
never API keys. A configured LLM is required for real digests; offline `preview`
works without one. See the [provider setup guide](../docs/platform-setup.md).

For embedding, record a genuine HTTPS image asset in `url`, the original
`source_url`, a figure-specific CC0 or CC BY license in `license`,
`license_scope: "figure"`, and the required `attribution`; then use
`images.mode: "embed"`. Do not infer figure rights from the article's open-access
status. Unsupported or incomplete metadata stays link-only. An embedded remote
image can be blocked by email clients and is loaded from its host when displayed.
