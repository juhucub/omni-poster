from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.models import (
    AccountCreate, AccountOut, MetricsOut, GoalIn, Message
)
from app.services.accounts import (
    _ACCOUNTS, create_account, fetch_metrics,
    delete_account, reconnect
)

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.post("/", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def add_account(payload: AccountCreate):
    acct_id = create_account(payload.platform, payload.oauth_code)
    data = _ACCOUNTS[acct_id].copy()
    data['stats'] = fetch_metrics(acct_id)
    return AccountOut(**data)

@router.get("/", response_model=List[AccountOut])
def list_accounts():
    result = []
    for acct in _ACCOUNTS.values():
        copy = acct.copy()
        copy['stats'] = fetch_metrics(acct['id'])
        result.append(copy)
    return result

@router.get("/{account_id}/metrics", response_model=MetricsOut)
def get_metrics(account_id: int):
    acct = _ACCOUNTS.get(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    stats = fetch_metrics(account_id)
    return MetricsOut(**stats)

@router.post("/{account_id}/goals", response_model=Message)
def set_goals(account_id: int, goals: GoalIn):
    acct = _ACCOUNTS.get(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    acct['goals'] = goals.dict(exclude_none=True)
    return Message(detail="Goals updated")

@router.delete("/{account_id}", response_model=Message)
def remove_account(account_id: int):
    if account_id not in _ACCOUNTS:
        raise HTTPException(status_code=404, detail="Account not found")
    delete_account(account_id)
    return Message(detail="Account removed")

@router.patch("/{account_id}/reconnect", response_model=Message)
def patch_reconnect(account_id: int):
    if not reconnect(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return Message(detail="Token refreshed")
