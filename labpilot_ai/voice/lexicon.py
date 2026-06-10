import difflib
import re
from pathlib import Path

import yaml


DEFAULT_TERMS = [
    "labscript",
    "runmanager",
    "BLACS",
    "lyse",
    "single lyse",
    "multi lyse",
    "Rabi",
    "Ramsey",
    "TOF",
    "BEC",
    "SG",
    "spin mixing",
    "spin exchange",
    "Bayesian optimization",
    "grid search",
    "duration_tof_ms",
    "N_total",
    "rho_0",
    "temperature_uK",
]


COMMON_CORRECTIONS = {
    "run manger": "runmanager",
    "run manager": "runmanager",
    "black's": "BLACS",
    "blax": "BLACS",
    "lies": "lyse",
    "lice": "lyse",
    "to f": "TOF",
    "t o f": "TOF",
    "rabi": "Rabi",
    "ramsey": "Ramsey",
}


class VoiceLexicon:
    def __init__(self, terms=None, corrections=None):
        self.terms = sorted({str(term).strip() for term in (terms or []) if str(term).strip()}, key=len, reverse=True)
        self.corrections = {str(k).lower(): str(v) for k, v in (corrections or {}).items()}

    @classmethod
    def from_registries(cls, global_registry=None, blacs_registry=None, lyse_registry=None, extra_path=None):
        terms = list(DEFAULT_TERMS)
        corrections = dict(COMMON_CORRECTIONS)
        for registry in [global_registry or {}, blacs_registry or {}]:
            for name, rule in registry.items():
                terms.append(name)
                terms.extend(rule.get("aliases", []) or [])
                if rule.get("description"):
                    terms.extend(_important_words(rule.get("description", "")))
        lyse_registry = lyse_registry or {}
        for group in ["single_modules", "multi_modules"]:
            for name, cfg in (lyse_registry.get(group, {}) or {}).items():
                terms.append(name)
                terms.extend((cfg.get("params", {}) or {}).keys())
        if extra_path:
            data = load_lexicon_file(extra_path)
            terms.extend(data.get("terms", []) or [])
            corrections.update(data.get("corrections", {}) or {})
        return cls(terms=terms, corrections=corrections)

    def prompt(self, limit=120) -> str:
        selected = self.terms[:limit]
        if not selected:
            return ""
        return (
            "This is a Chinese and English labscript control command. "
            "Preserve these scientific/code terms exactly when heard: "
            + ", ".join(selected)
            + "."
        )

    def correct_text(self, text: str) -> str:
        out = str(text or "")
        for wrong, right in self.corrections.items():
            out = re.sub(re.escape(wrong), right, out, flags=re.IGNORECASE)
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_ .-]{1,40}|[\u4e00-\u9fff]+|[^\s]", out)
        corrected = []
        searchable_terms = [term for term in self.terms if _is_identifier_like(term)]
        for token in tokens:
            stripped = token.strip()
            if _is_identifier_like(stripped):
                match = fuzzy_match(stripped, searchable_terms)
                corrected.append(match or token)
            else:
                corrected.append(token)
        return _join_tokens(corrected).strip()


def load_lexicon_file(path):
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fuzzy_match(token, terms, min_ratio=0.88):
    low = token.lower().replace(" ", "")
    best = None
    best_ratio = 0.0
    for term in terms:
        ratio = difflib.SequenceMatcher(None, low, term.lower().replace(" ", "")).ratio()
        if ratio > best_ratio:
            best = term
            best_ratio = ratio
    return best if best_ratio >= min_ratio else None


def _important_words(text):
    return [word for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text) if len(word) >= 3]


def _is_identifier_like(text):
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_ .-]{1,40}", str(text or "")))


def _join_tokens(tokens):
    out = ""
    for token in tokens:
        if not out:
            out = token
        elif re.fullmatch(r"[\u4e00-\u9fff]+", token) or re.fullmatch(r"[\u4e00-\u9fff]+", out[-1]):
            out += token
        elif token in ".,:;!?，。；：！？":
            out += token
        else:
            out += " " + token
    return out
