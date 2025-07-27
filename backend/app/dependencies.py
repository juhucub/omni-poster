from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
import jwt
import logging
from typing import Optional
from app.services.auth import SECRET_KEY, ALGORITHM, _users_db
from app.models import User

logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Cookie(None)
) -> User:
    """
    Get current user from either Authorization header or access_token cookie.
    """
    logger.info(f"Auth attempt - Header token: {'Yes' if token else 'No'}, Cookie: {'Yes' if access_token else 'No'}")
    
    # Try cookie first (matches your frontend approach)
    auth_token = access_token or token
    
    if not auth_token:
        logger.warning("No authentication token found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - missing token"
        )
    
    try:
        logger.info(f"Decoding token: {auth_token[:20]}...")  # Log first 20 chars
        payload = jwt.decode(auth_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        logger.info(f"Token decoded successfully for user: {username}")
        
        if not username or username not in _users_db:
            logger.warning(f"User not found: {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Could not validate credentials"
            )
        
        logger.info(f"Authentication successful for user: {username}")
        return _users_db[username]
        
    except jwt.PyJWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=f"Invalid token: {str(e)}"
        )