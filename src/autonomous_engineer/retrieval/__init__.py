"""
retrieval -- Code retrieval and context assembly for issue resolution.

Public API:
  - ContextRetriever: Main unified retrieval orchestrator.
  - LexicalRetriever: Multi-signal lexical code and symbol retriever.
  - LexicalWeights: Configuration weights for lexical matching.
  - StructuralRetriever: AST graph expansion retriever.
  - StructuralWeights: Configuration weights for structural expansion.
  - CodeTokenizer: Sub-identifier and code-aware tokenizer.
  - LocalImportResolver: Static local Python import resolver.
  - RetrievalEvaluator: Information Retrieval evaluation harness.
  - RetrievalBenchmarkTestCase, RetrievalMetrics: Evaluation data models.
"""
from __future__ import annotations

from autonomous_engineer.retrieval.combined import ContextRetriever
from autonomous_engineer.retrieval.evaluation import (
    CaseEvaluationResult,
    DetailedEvaluationReport,
    RetrievalBenchmarkTestCase,
    RetrievalEvaluator,
    RetrievalMetrics,
)
from autonomous_engineer.retrieval.import_resolver import LocalImportResolver
from autonomous_engineer.retrieval.lexical import LexicalRetriever, LexicalWeights
from autonomous_engineer.retrieval.structural import StructuralRetriever, StructuralWeights
from autonomous_engineer.retrieval.tokenizer import CodeTokenizer

__all__ = [
    "CaseEvaluationResult",
    "CodeTokenizer",
    "ContextRetriever",
    "DetailedEvaluationReport",
    "LexicalRetriever",
    "LexicalWeights",
    "LocalImportResolver",
    "RetrievalBenchmarkTestCase",
    "RetrievalEvaluator",
    "RetrievalMetrics",
    "StructuralRetriever",
    "StructuralWeights",
]
