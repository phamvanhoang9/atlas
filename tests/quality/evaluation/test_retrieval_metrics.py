from src.quality.evaluation.retrieval_metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_recall_and_precision_at_k() -> None:
    retrieved = ["a", "b", "c", "d"]
    relevant = ["b", "d", "x"]

    assert recall_at_k(retrieved, relevant, 2) == 0.3333
    assert precision_at_k(retrieved, relevant, 2) == 0.5
    assert recall_at_k(retrieved, relevant, 4) == 0.6667


def test_ndcg_at_k_with_graded_relevance() -> None:
    retrieved = ["doc1", "doc2", "doc3"]
    relevance = {"doc1": 3.0, "doc2": 0.0, "doc3": 2.0}

    score = ndcg_at_k(retrieved, relevance, 3)

    assert 0.85 < score < 0.95
