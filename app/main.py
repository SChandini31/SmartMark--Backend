from fastapi import FastAPI

from app.db.database import test_database_connection
from app.routes.resources import router as resources_router
from app.routes.auth import router as auth_router
from app.routes.collections import router as collections_router
from app.routes.tags import router as tags_router
from app.routes.search import router as search_router


app = FastAPI(
    title="SmartMark API",
    description="Personal Information Retrieval and Knowledge Management System",
    version="1.0.0"
)

app.include_router(auth_router)
app.include_router(resources_router)
app.include_router(collections_router)
app.include_router(tags_router)
app.include_router(search_router)

@app.get("/")
def root():
    return {
        "message": "SmartMark API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/db-test")
def database_test():
    connected = test_database_connection()

    if connected:
        return {
            "database": "connected"
        }

    return {
        "database": "connection failed"
    }