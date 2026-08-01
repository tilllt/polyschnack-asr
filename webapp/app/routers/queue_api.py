"""Queue watcher API (Task 7) — position, status, backend; foreign jobs anonymised.

Foreign jobs are shown without filename and without user linkage: only
``#job_id``, position, status, backend and eta_s. Admins see everything
(``is_mine`` true for all jobs they inspect via the admin panel).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..queue import queue_manager
from ..service_registry import total_concurrency

router = APIRouter(prefix="/api")


def _current_user(request, session=None) -> Optional[int]:
    from ..anon_session import current_uid

    return current_uid(request, session)


def _is_admin(request: Request) -> bool:
    if not settings.OIDC_ENABLED:
        return False
    return bool(request.session.get("is_admin"))


@router.get("/queue")
def list_queue(request: Request, session: Session = Depends(get_session)) -> dict:
    """Active queue: own jobs with position, foreign jobs anonymised."""
    uid = _current_user(request, session)
    jobs = queue_manager.list(uid, _is_admin(request))
    return {"jobs": jobs, "concurrency": total_concurrency()}


@router.delete("/queue/{job_id}")
def cancel_queue_job(job_id: int, request: Request,
                     session: Session = Depends(get_session)) -> dict:
    """Cancel a queued job (owner or admin). 404 when not cancellable."""
    uid = _current_user(request, session)
    if not queue_manager.cancel(job_id, uid, _is_admin(request)):
        raise HTTPException(status_code=404, detail="job not found or not cancellable")
    return {"cancelled": job_id}
