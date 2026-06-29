"""GitCast 应用入口点。

启动方式：
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from api.app import create_app

app: FastAPI = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
