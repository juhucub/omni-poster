from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.accounts import router as accounts_router
from app.routers.upload import router as upload_router
from .db import Base, engine
from app.routers.crawl import router as crawl_router
#initialize app

app = FastAPI(title="Unified Social Media Uploader Backend")
Base.metadata.create_all(bind=engine)  # Create database tables dev only

#Cross Origin Rules to serve React and API servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Adjust as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#include routers
app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(upload_router)
app.include_router(crawl_router)



