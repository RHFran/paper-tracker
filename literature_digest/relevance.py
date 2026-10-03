"""Transparent recall-oriented rules. A match is a candidate, not a quality rating."""
import re
import unicodedata
from .models import Paper

BVOC_QUERIES = [
    'biogenic volatile organic compounds',
    'BVOC emissions',
    'isoprene vegetation emissions',
    'monoterpene plant emissions',
    'sesquiterpene forest emissions',
    'plant volatile organic compounds',
    'soil microbial biogenic volatile organic compounds',
    'marine biogenic volatile organic compounds',
]
TREE_QUERIES = [
    'tree species classification remote sensing',
    'tree species identification hyperspectral',
    'tree species mapping lidar',
    'tree species discrimination satellite UAV',
    'tree species mapping synthetic aperture radar',
    'tree species classification terrestrial laser scanning',
]


def _classify_legacy(p: Paper) -> list[str]:
    t = f"{p.title} {p.abstract}".lower()
    bio_text = re.sub(r"\b(?:power|chemical|industrial|manufacturing|treatment)\s+plants?\b", "", t)
    bio = bool(re.search(r"\b(biogenic|plant[s]?|vegetation|forest[s]?|tree[s]?|leaf|leaves|foliar|canop\w*|ecosystem[s]?|microbial|bacteri\w*|fung\w*|alga\w*|phytoplankton|marine|soil)\b", bio_text))
    explicit = bool(re.search(r"biogenic volatile organic|biogenic\W+voc|plant volatile organic|植物.*挥发|生物源.*挥发", bio_text))
    acronym = bool(re.search(r"\bbvocs?\b", t))
    compound = bool(re.search(r"\b(isoprene|monoterpen\w*|sesquiterpen\w*|volatile organic compounds?|volatile emissions?|vocs?)\b", t))
    emission = bool(re.search(r"\b(emission[s]?|flux\w*|biosynth\w*|synthas\w*|atmospher\w*|volatili\w*|volatile|aerosol[s]?|oxidation|ozone|chemistry|signall?ing)\b", t))
    # BVOC plus atmospheric/emission context is meaningful even if the abstract is absent.
    bvoc = explicit or (acronym and (bio or emission)) or (bio and compound and emission)
    species = bool(re.search(r"(?:tree|forest|woody)[\s-]+species|树种", t))
    sensor = bool(re.search(r"remote sens\w*|hyperspectral|multispectral|\blidar\b|laser scanning|\buav\b|\bdrone\w*|satellite|sentinel[- ]?2|landsat|airborne|photogrammetr\w*|aerial imagery|synthetic aperture radar|\bsar\b|遥感|高光谱|激光雷达", t))
    task = bool(re.search(r"classif\w*|identif\w*|discriminat\w*|recogn\w*|mapping|delineat\w*|识别|分类", t))
    return (["bvoc"] if bvoc else []) + (["tree_species"] if species and sensor and task else [])



def _match_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[-‐‑‒–—]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def literal_phrase_in(phrase: str, text: str) -> bool:
    """Literal Unicode-aware phrases; topic strings are never regular expressions."""
    phrase, text = _match_text(phrase), _match_text(text)
    if not phrase:
        return False
    # CJK writing generally has no spaces between words. Latin/Cyrillic/etc.
    # require token boundaries, so "cat" does not match "catalyst".
    def unsegmented(char):
        return any(a <= ord(char) <= b for a, b in ((0x3400, 0x9fff), (0x3040, 0x30ff), (0xac00, 0xd7af), (0x20000, 0x3134f)))
    left = r"(?<!\w)" if phrase[0].isalnum() and not unsegmented(phrase[0]) else ""
    right = r"(?!\w)" if phrase[-1].isalnum() and not unsegmented(phrase[-1]) else ""
    return bool(re.search(left + re.escape(phrase) + right, text))


def classify(p: Paper, topics: list[dict] | None = None) -> list[str]:
    if not topics:
        return _classify_legacy(p)
    text = f"{p.title} {p.abstract}"
    tracks = []
    for topic in topics:
        include_any, include_all = topic.get("include_any", []), topic.get("include_all", [])
        # Query-only topics remain usable, but source retrieval alone is not a match.
        positive = include_any or ([] if include_all else topic.get("queries", []))
        if positive and not any(literal_phrase_in(term, text) for term in positive):
            continue
        if not positive and not include_all:
            continue
        if not all(literal_phrase_in(term, text) for term in include_all):
            continue
        if any(literal_phrase_in(term, text) for term in topic.get("exclude_any", [])):
            continue
        tracks.append(topic["id"])
    return list(dict.fromkeys(tracks))


def merge_papers(papers: list[Paper], topics: list[dict] | None = None) -> list[Paper]:
    """Merge explicit identifiers only, never title similarity or version relations."""
    groups: list[Paper] = []
    aliases: dict[str, Paper] = {}
    for p in papers:
        matches = {id(aliases[a]): aliases[a] for a in p.aliases if a in aliases}
        if not matches:
            groups.append(p)
            for a in p.aliases:
                aliases[a] = p
            continue
        target = next(iter(matches.values()))
        for other in list(matches.values())[1:] + [p]:
            if other is target:
                continue
            old_aliases = other.aliases
            if not target.doi:
                target.doi = other.doi
            if len(other.abstract) > len(target.abstract):
                target.abstract = other.abstract
            if not target.authors:
                target.authors, target.author_details = other.authors, other.author_details
            elif target.authors == other.authors and not target.author_details:
                target.author_details = other.author_details
            for name in ("pmcid", "arxiv_id", "journal"):
                if not getattr(target, name):
                    setattr(target, name, getattr(other, name))
            if len(other.full_text) > len(target.full_text):
                target.full_text, target.full_text_url = other.full_text, other.full_text_url
            target.open_access = target.open_access or other.open_access
            target.source_aliases = sorted(set(target.source_aliases + old_aliases))
            # Keep every provider's original date fields; the pipeline reconciles them.
            for name in ("provenance", "warnings", "relations", "figures"):
                values = getattr(target, name)
                values.extend(value for value in getattr(other, name) if value not in values)
            if "预印本" in other.kind and "预印本" not in target.kind:
                target.kind = "含预印本来源；发表与评审状态需核实"
            for a in old_aliases:
                aliases[a] = target
            if other is not p:
                groups.remove(other)
                for a, existing in list(aliases.items()):
                    if existing is other:
                        aliases[a] = target
        for a in target.aliases:
            aliases[a] = target
    for p in groups:
        p.tracks = classify(p, topics)
        p.evidence_level = "全文正文（不含图像像素、外部补充材料；表格格式可能丢失）" if p.full_text else "仅摘要" if p.abstract else "仅元数据"
    return groups
