from fastapi import APIRouter

from src.api.v1 import agent, auth, categories, data, docs, feishu

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(categories.router)
api_router.include_router(data.router)
api_router.include_router(docs.router)
api_router.include_router(feishu.router)
api_router.include_router(agent.router)
