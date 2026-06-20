"""History REST routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from src.api import deps
from src.api.middleware.auth import require_api_auth

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def get_history(limit: Optional[int] = None, _: None = Depends(require_api_auth)) -> JSONResponse:
    """Get all history entries."""
    try:
        entries = await deps.run_sync(deps.history_manager.get_all_entries, limit=limit)
        return JSONResponse(content={"success": True, "data": entries})
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/export")
async def export_history(_: None = Depends(require_api_auth)) -> FileResponse:
    """Export history to a JSON file."""
    try:
        export_path = "outputs/history_export.json"
        await deps.run_sync(deps.history_manager.export_to_json, export_path)
        return FileResponse(export_path, filename="history_export.json")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/stats")
async def get_history_stats(_: None = Depends(require_api_auth)) -> JSONResponse:
    """Get history statistics."""
    try:
        stats = await deps.run_sync(deps.history_manager.get_statistics)
        return JSONResponse(content={"success": True, "data": stats})
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/search/{search_term}")
async def search_history(search_term: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    """Search history entries."""
    try:
        results = await deps.run_sync(deps.history_manager.search_entries, search_term)
        return JSONResponse(content={"success": True, "data": results})
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{entry_id}")
async def get_history_entry(entry_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    """Get a specific history entry."""
    entry = await deps.run_sync(deps.history_manager.get_entry, entry_id)
    if entry:
        return JSONResponse(content={"success": True, "data": entry})
    raise HTTPException(status_code=404, detail="Entry not found")


@router.delete("/{entry_id}")
async def delete_history_entry(entry_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    """Delete a history entry. If it was a daily report, its automation run is
    removed too so Recent runs keeps mirroring the daily reports that exist."""
    success = await deps.run_sync(deps.history_manager.delete_entry, entry_id)
    if success:
        await deps.run_sync(deps.automation_store.delete_runs_by_history_id, entry_id)
        return JSONResponse(content={"success": True, "message": "Entry deleted"})
    raise HTTPException(status_code=404, detail="Entry not found")


@router.delete("")
async def clear_history(_: None = Depends(require_api_auth)) -> JSONResponse:
    """Clear all history. Also clears automation Recent runs so the UI stays consistent."""
    try:
        await deps.run_sync(deps.history_manager.clear_all)
        await deps.run_sync(deps.automation_store.clear_runs)
        return JSONResponse(content={"success": True, "message": "History cleared"})
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
