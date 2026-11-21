"""Why-this-label explanations (N3): the words that pushed each head towards its predicted class.

Owner: B (Shishir). sentinel/pipeline.py calls it and fills `result.explanations`; Kaushik's panel shows it.

Contract (keep stable):
    explain(model: TriageModel, text: str, top_n: int = 3) -> dict[str, list[str]]
    -> {"type": ["bricht ständig ab", ...], "queue": [...], "priority": [...]}

How: the triage heads are linear over [word tf-idf | char tf-idf]. For the predicted class c of a head,
word feature j contributes  x_j * (w_cj - mean_k w_kj)  to the logit of c relative to the other classes
(softmax ignores a shift shared by all classes, so this is the part that decides the label). Rank the
word 1-2-gram features of THIS ticket by that contribution, keep the positive ones, drop stopword-only
and digit-only n-grams and n-grams that share a content word with a stronger phrase, trim edge stopwords
("the firewall" -> "firewall"), and return them as written in the ticket (original casing). Character n-grams are skipped; agents cannot read "rbin".

Calibration does not matter here: temperature scaling never changes the label or the ranking, and the
raw linear heads are `model.heads[head]`. The predicted class is the calibrated argmax, so it matches the
label the pipeline shows.

Fast: about 0.5 ms right after `model.predict()` on the same ticket (the pipeline's order; the tf-idf rows
are reused), 1-3 ms standalone (one vectorizer pass). Per-model coefficient arrays are cached. Never
raises: an unusable model gives {}, an empty or wordless ticket gives an empty list per head.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

HEADS = ("type", "queue", "priority")

# Function words that carry no reason on their own. A bigram is dropped only if BOTH words are here.
STOPWORDS = frozenset(
    """
    a an and are as at be been but by can could did do does for from had has have he her his how i if in
    into is it its me my no not of on or our she so than that the their them then there these they this to
    up us was we were what when where which who will with would you your am any all also just very
    aber als am an auch auf aus bei bin bis da das dass dem den der des die dies diese dieser doch du ein eine
    einem einen einer es für hat haben ich ihr im in ist ja kann mein meine mich mir mit nach nicht noch nur
    oder sein sich sie sind so über um und uns unser unsere vom von vor war was wenn wie wir wird zu zum zur
    wurde wurden werden habe hatte ihre ihren ihnen können könnte sehr since after before because seit weil about mehr out
    """.split()
)


def explain(model: Any, text: str, top_n: int = 3) -> dict[str, list[str]]:
    try:
        cache = _cache(model)
    except Exception:  # None, a test double, or a model without linear word features
        return {}
    try:
        return _explain(model, cache, text or "", max(int(top_n), 0))
    except Exception:  # never break triage over an explanation
        return {head: [] for head in cache["heads"]}


# -- internals ------------------------------------------------------------------------------


def _cache(model: Any) -> dict[str, Any]:
    """Per-model arrays: word feature names and centred word coefficients per head (built once)."""
    heads = model.heads
    cached = getattr(model, "_explain_cache", None)
    if cached is not None and all(cached["clf"].get(h) is heads[h] for h in heads):
        return cached

    word = dict(model.vectorizer.transformer_list)["word"]
    names = np.asarray(word.get_feature_names_out())
    n_word = len(names)
    coefs: dict[str, np.ndarray] = {}
    for head in HEADS:
        if head not in heads:
            continue
        w = np.asarray(heads[head].coef_)[:, :n_word]
        if w.shape[0] == 1:  # binary head: one row is the logit of classes_[1]
            w = np.vstack([-w[0], w[0]])
        coefs[head] = w - w.mean(axis=0, keepdims=True)
    cached = {"n_word": n_word, "names": names, "coefs": coefs, "heads": tuple(coefs),
              "clf": {h: heads[h] for h in heads}}
    try:
        model._explain_cache = cached
    except AttributeError:
        pass
    return cached


def _explain(model: Any, cache: dict[str, Any], text: str, top_n: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {head: [] for head in cache["heads"]}
    if top_n == 0 or not text.strip():
        return out

    # [word | char], exactly what the heads saw. TriageModel.features() reuses predict()'s pass on this text.
    X = model.features([text]) if hasattr(model, "features") else model.vectorizer.transform([text])
    xw = X[:, : cache["n_word"]].tocsr()
    if xw.nnz == 0:
        return out
    labels = _predicted_class_index(model, X, cache["heads"])
    cols, vals = xw.indices, xw.data

    for head in cache["heads"]:
        contrib = vals * cache["coefs"][head][labels[head], cols]
        order = np.argsort(-contrib)
        picked: list[tuple[str, ...]] = []
        for i in order:
            if contrib[i] <= 0 or len(picked) == top_n:
                break
            tokens = _trim(tuple(str(cache["names"][cols[i]]).split()))
            if not _readable(tokens) or any(_overlaps(tokens, p) for p, _ in picked):
                continue
            phrase = _as_written(text, tokens)
            if phrase is not None:
                picked.append((tokens, phrase))
        out[head] = [phrase for _, phrase in picked]
    return out


def _predicted_class_index(model: Any, X: Any, heads: tuple[str, ...]) -> dict[str, int]:
    """Row index into coef_ of the class the model shows (calibrated argmax when the model has one)."""
    from sentinel.triage import _calibrated_proba

    calibrators = getattr(model, "calibrators", {}) or {}
    return {h: int(np.argmax(_calibrated_proba(model.heads[h], calibrators.get(h), X)[0])) for h in heads}


def _trim(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Drop stopwords at the edges of a bigram: ("the", "firewall") -> ("firewall",)."""
    while len(tokens) > 1 and tokens[0] in STOPWORDS:
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1] in STOPWORDS:
        tokens = tokens[:-1]
    return tokens


def _readable(tokens: tuple[str, ...]) -> bool:
    if not tokens or all(t in STOPWORDS for t in tokens):
        return False
    return not all(t.isdigit() or t.replace("_", "").isdigit() for t in tokens)


def _overlaps(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """True if the phrases share a content word ("vpn" vs "vpn down", "firewall update" vs "the firewall")."""
    return bool((set(a) - STOPWORDS) & (set(b) - STOPWORDS))


def _as_written(text: str, tokens: tuple[str, ...]) -> str | None:
    """The phrase with the ticket's own casing ("VPN", "Rechnung"); lowercase if it cannot be found.

    None for a bigram that only exists across punctuation ("service? Thank"): the tokenizer ignores
    punctuation, but nobody wrote that phrase, so it is not shown.
    """
    seps = r"[\s\-/]+"  # words joined by spaces, hyphens or slashes still read as one phrase
    pattern = r"(?<!\w)" + seps.join(re.escape(t) for t in tokens) + r"(?!\w)"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if m:
        return m.group(0)
    if len(tokens) > 1:
        return None
    return tokens[0]
