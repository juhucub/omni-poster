import uuid
import os
import logging
from typing import Optional
from enum import Enum
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, UploadFile, File, BackgroundTasks, HTTPException, status, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from passlib.context import CryptContext
import jwt
from jose import JWTError

SECRET_KEY = os.getenv('SECRET_KEY', 'supersecretkey')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
USER_ID_COUNTER = 1  #simple in-memory user ID counter
#initialize app and logger
app = FastAPI(title="Unified Social Media Uploader Backend") #fast API instance
logger = logging.getLogger("uvicorn.error")

#password hashing 
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

#Cross Origin Rules to serve React and API servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Adjust as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

##########################
#configuration and helpers
###########################
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

#In memory stores for demo (FIXME use a real DB in prod)
JOBS: dict = {}     #job_id -> status/info
OAUTH_TOKENS: dict = {} #user_id -> tokens
USERS: dict[str, any] = {} #username -> {, hashed_password, created_at}


def save_file(file: UploadFile, dest_path: str) -> None:
    #saves uploaded file to disk in streaming chunks for mem efficiency
    try:
        with open(dest_path, "wb") as buffer:
            for chunk in file.file:
                buffer.write(chunk)
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise
    finally:
        file.file.close()

def get_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = ({"sub": subject, "exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

##########################
#Data models
###########################
class UploadResponse(BaseModel):
    project_id: str = Field(..., description="The ID of the created project") 

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"[a-zA-Z0-9_]+$")
    #email : emailStr
    password: str = Field(..., min_length=8)

    @validator('password')
    def validate_password_complexity(cls, v):
        if (not any(c.islower() for c in v) or
            not any(c.isupper() for c in v) or
            not any(c.isdigit() for c in v) or
            len(v) < 8):
            raise ValueError('Password must be at least 8 characters long and include uppercase, lowercase, and numeric characters.')
        return v

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)

class MeRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MeResponse(BaseModel):
    id: int
    username: str
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    username: str

##########################
#Endpoints
###########################
@app.post("/auth/register", response_model=TokenResponse)   
def register(request: RegisterRequest, response: Response): 
    #User Signup: validate input, hash password, prevent duplicates, issue JWT token and set HTTP-only cookie
    global USER_ID_COUNTER
    #prevent duplicates
    if request.username in USERS:
        logger.warning(f"Registration attempt with existing username")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    #if any(user['email'] == request.email for user in USERS.values()):
     #   logger.warning(f"Registration attempt with existing email")
      #  raise HTTPException(
      #      status_code=status.HTTP_400_BAD_REQUEST,
      #      detail="Email already registered"
      #  )
    
    #Hash password and store user
    hashed_pw = get_hash(request.password)
    user_id = USER_ID_COUNTER
    USER_ID_COUNTER += 1
    USERS[request.username] = {
        "id": user_id,
        "hashed_password": hashed_pw,
        "created_at": datetime.utcnow().isoformat()
    }
    logger.info(f"New user registered: {request.username}")

    #create JWT
    token = create_access_token( request.username )
    #Sett HTTP only cookie :3
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return TokenResponse(access_token=token)

@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, response: Response):
    # Verify user exists
    user = USERS.get(req.username)
    if not user or not verify_password(req.password, user['hashed_password']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Issue JWT
    token = create_access_token(req.username)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="lax")
    return TokenResponse(access_token=token)

@app.post("/auth/me", response_model=MeResponse)
def auth_me(request: MeRequest, response: Response):
    user = USERS.get(request.username)
    if not user or not verify_password(request.password, user['hashed_password']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(request.username)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="lax")
    return MeResponse(id=user['id'], username=request.username, access_token=token)

@app.get('/auth/me', response_model=UserResponse)
def get_current_user(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
):
    token = access_token or (authorization.split(' ')[1] if authorization and authorization.startswith('Bearer ') else None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get('sub')
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    user = USERS.get(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    return UserResponse(id=user['id'], username=username)

@app.post("/upload", response_model=UploadResponse)
async def upload(
    video: UploadFile = File(..., description="Raw video or images to be processed"),
    audio: UploadFile = File(..., description="Audio file (mp3/wav) to be processed"),
    thumbnail: Optional[UploadFile] = File(None, description="Thumbnail image for the video")
):
    # Accepts raw assets, saves to disk or cloud storage, and returns a project_id
    # Validates file types
    # Processes files as needed (e.g., extracting frames from video)

    #basic Validation
    for f, name in [(video, 'video'), (audio, 'audio')]:
        media_type = f.content_type.split('/')[0]
        if media_type not in ['video', 'audio', 'image']:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type for {name}. Expected video or audio. type : {f.content_type}"
            )
        project_id = str(uuid.uuid4())

        try:
            save_file(video, os.path.join(UPLOAD_DIR, f"{project_id}_video"))
            save_file(audio, os.path.join(UPLOAD_DIR, f"{project_id}_audio"))
            if thumbnail:
                save_file(thumbnail, os.path.join(UPLOAD_DIR, f"{project_id}_thumbnail"))   
        except Exception as e:
            logger.error(f"Failed to save files for project {project_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded files"
            )
        
        #initialize job status
        JOBS[project_id] = {"status": "uploaded"}

        return UploadResponse(project_id=project_id)

