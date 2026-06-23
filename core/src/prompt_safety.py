"""WS6 — neutralize untrusted free text before it enters an LLM prompt.

Profile prose (taste descriptors, ``core_description``), like/dislike reasons,
and artist/track names are user- or corpus-supplied and therefore untrusted. A
crafted value could try to inject a fake instruction, a fake chat turn, or a
fake fenced block to override the system prompt or break the Stage-3 JSON
contract (threat T3 / finding F6).

The defense is deliberately **structural** and a strict **no-op on legitimate
music text**, so it cannot regress recommendation quality — the evaluation
corpus renders to a byte-identical prompt. Only values that actually carry an
injection mechanic are altered:

  1. **Single-line collapse** — runs of CR/LF (plus the whitespace hugging
     them) become a single space. A one-line value cannot forge a new prompt
     line, a ``System:`` / ``Assistant:`` turn, or a fenced block on its own
     line. Pure inline whitespace with no newline is left untouched, so a
     normal single-line label is unchanged.
  2. **Fence defang** — triple backtick / triple tilde runs are removed so the
     value cannot open or close a Markdown/code block.
  3. **Override defang** — a small set of unambiguous instruction-override
     phrases ("ignore previous instructions", "disregard the system prompt",
     …) and start-of-line role markers are replaced with ``[filtered]``. These
     never legitimately appear in music metadata.

Defense-in-depth, not the only layer: the system prompt still carries an
explicit SECURITY directive, and model output is schema-normalized and
constrained to the approved-artist allow-list + known-track inventory, so a
value that slips through cannot make the app recommend arbitrary tracks.
"""
from __future__ import annotations

import re

# CR/LF (plus any horizontal whitespace hugging them) → single space. Inline
# whitespace with no newline is intentionally NOT matched, so a single-line
# value is a strict no-op.
_NEWLINE_RUN = re.compile(r"[ \t\f\v]*[\r\n]+[ \t\f\v]*")

# Triple backticks / triple tildes that could open or close a code block.
_CODE_FENCE = re.compile(r"`{3,}|~{3,}")

# Start-of-line fake chat-turn role markers, e.g. "System:", "Assistant:".
# Applied with MULTILINE before the newline collapse so per-line markers are
# caught. "user" is intentionally excluded — "user: likes X" is plausible data.
_ROLE_TURN = re.compile(
    r"(?im)^[ \t>*\-]*(system|assistant|developer|tool)[ \t]*:",
)

# Unambiguous instruction-override phrases. Defanged (not deleted) so the
# surrounding descriptive text survives for the model to read as data.
_OVERRIDE = re.compile(
    r"(?i)("
    r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|preceding|"
    r"earlier|foregoing|former)\s+"
    r"(?:instruction|instructions|prompt|prompts|message|messages|rule|rules|"
    r"constraint|constraints|direction|directions)"
    r"|disregard\s+(?:all\s+|any\s+|the\s+)?(?:previous\s+|prior\s+|above\s+|"
    r"preceding\s+)?(?:instruction|instructions|prompt|prompts|rule|rules|"
    r"constraint|constraints|system\s+prompt)"
    r"|forget\s+(?:everything|all|the|your|previous|prior)\b[^.\n]{0,40}?"
    r"(?:instruction|instructions|prompt|prompts|rule|rules|said|told)"
    r"|override\s+(?:the\s+)?(?:system|instruction|instructions|rule|rules|prompt)"
    r"|system\s+prompt"
    r"|new\s+instructions?\s*:"
    r")"
)

_FILTERED = "[filtered]"


def neutralize_untrusted(text):
    """Return *text* with prompt-injection mechanics structurally defanged.

    A strict no-op for single-line music metadata (artist/track names, genre
    and trait labels) — only values containing newlines, code fences, role
    markers, or explicit override phrases are altered. Non-strings and empty
    strings pass through unchanged. Idempotent.
    """
    if not isinstance(text, str) or not text:
        return text
    out = _ROLE_TURN.sub(r"\1 -", text)
    out = _OVERRIDE.sub(_FILTERED, out)
    out = _CODE_FENCE.sub("", out)
    out = _NEWLINE_RUN.sub(" ", out)
    return out


def neutralize_list(values):
    """Neutralize every string in *values*, preserving order and non-strings."""
    if not isinstance(values, (list, tuple)):
        return values
    return [neutralize_untrusted(v) if isinstance(v, str) else v for v in values]
