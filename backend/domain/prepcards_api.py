from fastapi import APIRouter, Depends

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import scan
from domain import prepcards_service as service
from domain.prepcards_model import prepcards
from domain.prepcards_schemas import ClaimCard, IssueCard, PrepareCard

router = APIRouter()

@router.get('/prepcards')
def list_prepcards(user=Depends(actor)):
    with transaction() as conn:
        return scan(conn, prepcards)


@router.post('/prepcards/prepare')
def prepare_card(data: PrepareCard, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.prepare_card(conn, user, data)
        record(conn, user, 'prepcards.prepare_card')
        return output


@router.post('/prepcards/issue')
def issue_card(data: IssueCard, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.issue_card(conn, user, data)
        record(conn, user, 'prepcards.issue_card')
        return output


@router.post('/prepcards/claim')
def claim_card(data: ClaimCard, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.claim_card(conn, user, data)
        record(conn, user, 'prepcards.claim_card')
        return output
