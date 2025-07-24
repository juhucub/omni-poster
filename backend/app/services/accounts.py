import logging, time
from typing import Dict
from threading import Lock

logger = logging.getLogger("uvicorn.error")

# In-memory demo store use real DB later
JOBS = {}
_ACCOUNTS = {}
_NEXT_ID = 1
_LOCK = Lock()

def save_tokens(account_id: int, tokens: Dict[str,str]):
    # encrypt & store in real secrets manager instead
    _ACCOUNTS[account_id]['tokens'] = tokens

def fetch_metrics(account_id: int) -> Dict[str,int]:
    #Simulate an API call + simple rate‐limit warning.
    acct = _ACCOUNTS[account_id]
    # TODO: use platform SDKs here
    stats = {"followers": 1000 + account_id, "views": 5000 + account_id, "likes": 200 + account_id}
    # simulate token expiry
    if time.time() % 60 < 5:
        acct['status'] = 'token_expired'
    return stats

def create_account(platform: str, oauth_code: str) -> int:
    global _NEXT_ID
    with _LOCK:
        acct_id = _NEXT_ID
        _NEXT_ID += 1
        _ACCOUNTS[acct_id] = {
            "id": acct_id,
            "platform": platform,
            "name": f"{platform.title()} User {acct_id}",
            "profile_picture": f"https://placekitten.com/64/64?u={acct_id}",
            "status": "authorized",
            "tokens": {"access": "fake-"+oauth_code}
        }
    return acct_id

def delete_account(account_id: int):
    _ACCOUNTS.pop(account_id, None)

def reconnect(account_id: int) -> bool:
    #Simulate token refresh
    acct = _ACCOUNTS.get(account_id)
    if not acct:
        return False
    acct['tokens']['access'] = "refreshed-"+str(time.time())
    acct['status'] = 'authorized'
    return True
