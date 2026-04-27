from types import SimpleNamespace

from src.rag.reranking import CrossEncoderReranker


class FakeCrossEncoder:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [0.1 if "weak" in pair[1] else 0.9 for pair in pairs]


def test_cross_encoder_disabled_keeps_original_order() -> None:
    documents = [
        SimpleNamespace(page_content="weak result"),
        SimpleNamespace(page_content="strong result"),
    ]
    reranker = CrossEncoderReranker(enabled=False)

    assert reranker.rerank_documents("query", documents) == documents


def test_cross_encoder_reranks_with_loaded_model() -> None:
    documents = [
        SimpleNamespace(page_content="weak result"),
        SimpleNamespace(page_content="strong result"),
    ]
    reranker = CrossEncoderReranker(enabled=True)
    reranker._model = FakeCrossEncoder()

    ranked = reranker.rerank_documents("query", documents)

    assert ranked[0].page_content == "strong result"
    assert ranked[1].page_content == "weak result"
