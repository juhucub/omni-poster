import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
#from app.routers.accounts import router as accounts_router

#initialize app

app = FastAPI(title="Unified Social Media Uploader Backend")

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
#app.include_router(accounts_router)




