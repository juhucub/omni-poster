from fastapi import APIRouter, Response, Depends, HTTPException, status
from app.models import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    MeResponse,
    MeRequest,
    UserResponse,
)
from app.services.auth import (
    register_user,
    authenticate_user,
    create_access_token,
    USERS,
)
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(request: RegisterRequest, response: Response):
    try:
        register_user(request.username, request.password)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already exists")

    token = create_access_token(request.username)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, response: Response):
    if not authenticate_user(request.username, request.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    token = create_access_token(request.username)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return TokenResponse(access_token=token)


@router.post("/me", response_model=MeResponse)
def reauth(request: MeRequest, response: Response):
    # re-issue a fresh token on valid credentials
    if not authenticate_user(request.username, request.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    token = create_access_token(request.username)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return MeResponse(id=USERS[request.username]["id"],
                      username=request.username,
                      access_token=token)


@router.get("/me", response_model=UserResponse)
def whoami(current: UserResponse = Depends(get_current_user)):
    return current
