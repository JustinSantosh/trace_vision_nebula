"""Multi-frame plate fusion (judged algorithm, PIPELINE.md section 4).

Takes several single-frame OCR reads of the same plate and returns one plate string, writing '?' for
every position where the evidence is not strong or consistent enough. It never fills in a guess.

A read is a dict:
    {"frame": 120, "quality": 0.8,                    # quality in 0..1 (sharpness, plate size, ...)
     "chars": [{"char": "C", "prob": 0.99, "top3": [["C", 0.99], ["G", 0.005], ["O", 0.001]]}, ...]}
`top3` is optional. The Awiros wrapper (`awiros_feasibility_check.ctc_decode`) produces exactly this.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

from . import load_config
from .plates import best_template, char_class, coerce, format_warnings, is_lookalike, normalise


@dataclass
class Position:
    pos: int                    # 1-based
    char: str                   # decided character or '?'
    confidence: float           # quality-weighted mean OCR probability of `char` (0 if '?')
    share: float                # share of the weighted vote won by the best candidate
    support: int                # number of reads covering this position
    best_candidate: str         # best candidate even when '?' was emitted (for the report, never the plate)
    frames: list = field(default_factory=list)   # frames whose top-1 read agrees with `char`


@dataclass
class FusedPlate:
    text: str
    positions: list
    template: str
    n_reads: int
    unknown_positions: list
    warnings: list

    def to_dict(self):
        return asdict(self)


def _read_text(read):
    return normalise("".join(c["char"] for c in read["chars"]))


def _sub_cost(a, b):
    return 0.0 if a == b else 0.3 if is_lookalike(a, b) else 1.0


def _align(ref: str, s: str):
    """Edit-distance alignment. Returns (cost, mapping ref_index -> s_index or None)."""
    n, m = len(ref), len(s)
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        D[i][0] = float(i)
    for j in range(1, m + 1):
        D[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j - 1] + _sub_cost(ref[i - 1], s[j - 1]), D[i - 1][j] + 1, D[i][j - 1] + 1)
    mapping, i, j = [None] * n, n, m
    while i > 0 and j > 0:
        if D[i][j] == D[i - 1][j - 1] + _sub_cost(ref[i - 1], s[j - 1]):
            mapping[i - 1] = j - 1; i -= 1; j -= 1
        elif D[i][j] == D[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    return D[n][m], mapping


def fuse(reads: list, cfg: dict | None = None) -> FusedPlate:
    cfg = (cfg or load_config())["fusion"]
    reads = [r for r in reads if r.get("chars")]
    texts = [_read_text(r) for r in reads]
    keep = [i for i, t in enumerate(texts) if t]
    reads, texts = [reads[i] for i in keep], [texts[i] for i in keep]
    if not reads:
        return FusedPlate("", [], "unknown", 0, [], ["no readable OCR output"])

    # 1. reference = medoid read (smallest total alignment cost to the others); ties -> higher quality x mean prob
    def strength(r):
        ps = [c["prob"] for c in r["chars"]]
        return r.get("quality", 1.0) * (sum(ps) / len(ps))
    costs = [sum(_align(t, u)[0] for u in texts) for t in texts]
    ref_i = min(range(len(reads)), key=lambda i: (costs[i], -strength(reads[i])))
    ref = texts[ref_i]

    # 2. letter/digit class per position from the reference's best-fitting Indian template
    tpl_name, tpl = best_template(ref)
    classes = list(tpl) if tpl else [char_class(c) for c in ref]

    # 3. weighted votes per position
    votes = [defaultdict(float) for _ in ref]
    top1_prob = [defaultdict(float) for _ in ref]   # sum of q*p over reads whose TOP-1 is this char
    top1_q = [defaultdict(float) for _ in ref]      # sum of q over those reads
    q_cover = [0.0] * len(ref)
    support = [0] * len(ref)
    agree_frames = [defaultdict(list) for _ in ref]
    for r, t in zip(reads, texts):
        q = float(r.get("quality", 1.0))
        chars = [c for c in r["chars"] if normalise(c["char"])]
        _, mapping = _align(ref, t)
        for k, j in enumerate(mapping):
            if j is None or j >= len(chars):
                continue
            support[k] += 1
            q_cover[k] += q
            entry = chars[j]
            cands = [[entry["char"], entry["prob"]]]
            if cfg.get("use_top3") and entry.get("top3"):
                cands = [[c, p] for c, p in entry["top3"] if c not in ("<blank>", " ")]
            for rank, (c, p) in enumerate(cands):
                c = normalise(c)
                if not c:
                    continue
                w = 1.0
                if char_class(c) != classes[k]:
                    cc = coerce(c, classes[k])
                    if cc is None:
                        votes[k]["#invalid"] += q * p
                        continue
                    c, w = cc, cfg["cross_class_weight"]
                votes[k][c] += q * p * w
                if rank == 0:
                    top1_prob[k][c] += q * p * w
                    top1_q[k][c] += q
                    agree_frames[k][c].append(r.get("frame"))

    # 4. decide each position
    positions, out = [], []
    for k in range(len(ref)):
        total = sum(votes[k].values())
        valid = {c: v for c, v in votes[k].items() if c != "#invalid"}
        if not valid or total <= 0 or support[k] < cfg["min_support"]:
            positions.append(Position(k + 1, "?", 0.0, 0.0, support[k], "")); out.append("?"); continue
        best = max(valid, key=valid.get)
        share = valid[best] / total
        # confidence = quality-weighted mean probability among the reads that read `best` as their top-1;
        # disagreement is already measured by `share`, so it is not counted twice here.
        mean_prob = top1_prob[k][best] / top1_q[k][best] if top1_q[k][best] else 0.0
        ok = share >= cfg["tau_share"] and mean_prob >= cfg["tau_prob"]
        ch = best if ok else "?"
        positions.append(Position(k + 1, ch, round(mean_prob, 4) if ok else 0.0, round(share, 4), support[k], best,
                                  agree_frames[k].get(best, []) if ok else []))
        out.append(ch)
    text = "".join(out)
    unknown = [p.pos for p in positions if p.char == "?"]
    warnings = format_warnings(text)
    if len({len(t) for t in texts}) > 1:
        warnings.append(f"reads disagree on length {sorted({len(t) for t in texts})}; aligned to {len(ref)} characters")
    return FusedPlate(text, positions, tpl_name, len(reads), unknown, warnings)
