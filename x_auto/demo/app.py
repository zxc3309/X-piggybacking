"""
Static demo sub-app for the X auto-reply tool.

Serves a single public landing page at `/` with pre-written mock data so
visitors on Bill's personal website can experience the review dashboard
(approve / reject / edit / Second Brain panel / LLM reasoning) without any
real API calls being made.

Hard guarantees:
  - No import from x_auto.review or x_auto.workflow.
  - No network or Google Sheets calls at render time.
  - All state is client-side and resets every page load.

Mount in app.py:
    from x_auto.demo.app import app as demo_app
    app.mount("/demo", demo_app)
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from x_auto.demo import fixtures

app = FastAPI(
    title="X Auto-Reply Demo",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class EmbedHeadersMiddleware(BaseHTTPMiddleware):
    """Allow cross-origin iframe embedding on Bill's personal website."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Allow any parent frame. No X-Frame-Options header is set (modern
        # browsers honor CSP frame-ancestors over X-Frame-Options).
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
        if "x-frame-options" in response.headers:
            del response.headers["x-frame-options"]
        return response


app.add_middleware(EmbedHeadersMiddleware)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def demo_index(request: Request):
    """Render the single-post demo deep dive with fixtures embedded as JSON."""
    demo_data = {
        "item": fixtures.DEMO_ITEM,
        "pipeline": fixtures.PIPELINE_STEPS,
        "categories": fixtures.DEMO_CATEGORIES,
    }
    return templates.TemplateResponse(
        request,
        "demo.html",
        {"demo_data_json": json.dumps(demo_data)},
    )
