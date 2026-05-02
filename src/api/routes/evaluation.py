from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.api import deps
from src.api.middleware.auth import require_api_auth
from src.quality.evaluation import EvaluationInput, EvaluationRunner, GeneratedOutput

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

_EVALUATION_RESULTS: dict[str, dict] = {}


@router.post("/run")
async def run_evaluation(input_data: EvaluationInput, _: None = Depends(require_api_auth)) -> JSONResponse:
    runner = EvaluationRunner(enable_ragas=True)
    result = await runner.aevaluate_single(input_data)
    _EVALUATION_RESULTS[result.sample_id] = result.model_dump(mode="json")
    return JSONResponse(content={"success": True, "data": _EVALUATION_RESULTS[result.sample_id]})


@router.get("/{run_id}")
async def get_evaluation(run_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    result = _EVALUATION_RESULTS.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Evaluation result not found")
    return JSONResponse(content={"success": True, "data": result})


@router.get("/history/{history_id}")
async def evaluate_history(history_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    entry = await deps.run_sync(deps.history_manager.get_entry, history_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")

    runner = EvaluationRunner(enable_ragas=True)
    input_data = EvaluationInput(
        sample_id=history_id,
        query=entry["query"],
        retrieved_contexts=[],
        generated_output=GeneratedOutput(response=entry.get("report", "")),
        expected_behavior="answer",
        metadata={"mode": entry.get("mode"), "history_id": history_id},
    )
    result = await runner.aevaluate_single(input_data)
    _EVALUATION_RESULTS[history_id] = result.model_dump(mode="json")
    return JSONResponse(content={"success": True, "data": _EVALUATION_RESULTS[history_id]})
