"""
retrieval/tokenizer.py -- Sub-identifier and code-aware tokenizer.

Splits prose, camelCase, PascalCase, snake_case, and path identifiers into
normalized token sequences suitable for lexical code search.
"""
from __future__ import annotations

import re

# Standard English and programming stopwords to filter
STOPWORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "could", "did", "do", "does", "doing",
    "down", "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "s",
    "same", "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with", "would",
    "you", "your", "yours", "yourself", "yourselves",
    # Python syntactic stopwords
    "def", "class", "return", "self", "cls", "none", "true", "false", "import",
    "from", "pass", "raise", "except", "try", "finally", "with", "async", "await",
    "yield", "lambda", "global", "nonlocal", "assert", "del", "if", "elif", "else",
    "for", "while", "break", "continue",
})


def _split_camel_case(identifier: str) -> list[str]:
    """
    Split CamelCase or PascalCase string into constituent words.
    e.g. 'AuthenticationService' -> ['Authentication', 'Service']
         'HTTPResponse' -> ['HTTP', 'Response']
         'getHTTPResponse' -> ['get', 'HTTP', 'Response']
    """
    # Pattern to handle sequences of capitals followed by lowercase
    matches = re.finditer(
        r".+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)",
        identifier,
    )
    return [m.group(0) for m in matches if m.group(0)]


class CodeTokenizer:
    """Tokenizes queries and source code symbols for deterministic lexical retrieval."""

    def __init__(self, stopwords: frozenset[str] | None = None) -> None:
        self._stopwords = stopwords if stopwords is not None else STOPWORDS

    def tokenize_identifier(self, identifier: str) -> tuple[str, ...]:
        """
        Split a single code identifier (snake_case, camelCase, dot-path) into tokens.
        """
        tokens: list[str] = []

        # Split on non-alphanumeric chars (underscores, dots, dashes, slashes)
        parts = re.split(r"[\s_.\-\\/]+", identifier)

        for part in parts:
            if not part:
                continue
            camel_parts = _split_camel_case(part)
            for cp in camel_parts:
                clean = cp.strip().lower()
                if len(clean) >= 2 and clean not in self._stopwords:
                    tokens.append(clean)

        return tuple(tokens)

    def tokenize_text(self, text: str) -> tuple[str, ...]:
        """
        Tokenize a block of free-form text or issue description.
        Extracts code-like identifiers and words with sub-token splitting.
        """
        tokens: list[str] = []

        # Extract words and identifiers
        raw_words = re.findall(r"[a-zA-Z0-9_]+", text)

        for word in raw_words:
            id_tokens = self.tokenize_identifier(word)
            tokens.extend(id_tokens)

        return tuple(tokens)