from src.quality.evaluation.schemas import EvaluationSample


def test_golden_dataset_sample_schema() -> None:
    sample = EvaluationSample.model_validate(
        {
            "id": "sample-1",
            "query": "What is retrieval augmented generation?",
            "expected_behavior": "answer",
            "ground_truth_answer": None,
            "ground_truth_context": ["RAG retrieves external context."],
            "source_urls": ["https://example.com/rag"],
            "rubric": {
                "must_include": ["retrieval"],
                "must_not_include": ["private data"],
                "domain": "qa",
                "language": "en",
                "difficulty": "easy",
                "out_of_scope": False,
            },
        }
    )

    assert sample.id == "sample-1"
    assert sample.rubric.domain == "qa"
    assert sample.rubric.must_include == ["retrieval"]
