"""`POST /api/hub/companies`: a company describes what it needs. JSON, public,
rate-limited, mute -- the same three properties as the other two public writes. The
completion is reported to PostHog after the answer, as the freelancers' is
(`rebase_core.analytics`, REB-215)."""

from fastapi import APIRouter, BackgroundTasks, Request, status

from rebase_api.deps import SessionDep, TrackerDep
from rebase_api.ratelimit import spend_one
from rebase_core.companies import CompanyService
from rebase_core.schemas import Ack, CompanyCreate

router = APIRouter(prefix="/api/hub", tags=["hub"])


@router.post("/companies", response_model=Ack, status_code=status.HTTP_201_CREATED)
def request_people(
    data: CompanyCreate,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    tracker: TrackerDep,
) -> Ack:
    spend_one(request)
    CompanyService(session).request(data)
    if tracker is not None:
        background.add_task(tracker.application, "azienda", data.distinct_id, utm=data.utm)
    return Ack()
