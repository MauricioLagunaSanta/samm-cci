"""Aplicación FastAPI de SAMM-CCI.

    cd backend
    uvicorn app.main:app --reload        # API en http://127.0.0.1:8000  (documentación en /docs)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # crea las tablas y avisa con claridad si el esquema quedó desactualizado
    yield


app = FastAPI(title="SAMM-CCI", version="0.4.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite en desarrollo
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Filas", "X-Por-Revisar"],
)
app.include_router(router)
