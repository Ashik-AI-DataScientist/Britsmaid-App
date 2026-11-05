"""Serialize API business writes with cleanup and snapshot exports."""
import asyncio
from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.requests import Request
from service_lease import business_lease

class MediaReferenceGuard:
    def __init__(self, app, db, authenticate=None):
        self.app, self.db, self.authenticate = app, db, authenticate

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "DELETE")
                or not path.startswith("/api/") or path.endswith("/ical-sync") or path.startswith(("/api/auth/", "/api/system/", "/api/files/", "/api/sync", "/api/guest/"))):
            return await self.app(scope, receive, send)
        started = False
        async def response_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        try:
            if self.authenticate:
                await self.authenticate(Request(scope))
            async with business_lease(self.db, seconds=180):
                await asyncio.wait_for(self.app(scope, receive, response_send), timeout=120)
        except HTTPException as exc:
            if started:
                raise
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers={"Retry-After": "2"})(scope, receive, send)
        except asyncio.TimeoutError:
            if not started:
                await JSONResponse({"detail": "Update timed out. Refresh to check whether it was saved."}, status_code=408)(scope, receive, send)
