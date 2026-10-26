"""Bound API bodies before multipart parsing or JSON allocation grows unbounded."""
from fastapi import HTTPException
from starlette.responses import JSONResponse
import asyncio


class BoundedAPIBodies:
    def __init__(self, app):
        self.app = app
        self.upload_active = False
        self.upload_timeout = 110

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/upload" or scope.get("method") != "POST":
            return await self.handle(scope, receive, send)
        # This hosted build deliberately uses one worker. Admit before multipart parsing.
        if self.upload_active:
            return await JSONResponse({"detail": "Another upload is being processed. Please retry shortly."},
                status_code=429, headers={"Retry-After": "2"})(scope, receive, send)
        self.upload_active = True
        started = False
        async def upload_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        try:
            return await asyncio.wait_for(self.handle(scope, receive, upload_send), timeout=self.upload_timeout)
        except asyncio.TimeoutError:
            if not started:
                await JSONResponse({"detail": "Upload timed out. Check your connection and retry."}, status_code=408)(scope, receive, send)
        finally:
            self.upload_active = False

    async def handle(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/"):
            return await self.app(scope, receive, send)
        limit = (100 * 1024 * 1024 + 128 * 1024) if path == "/api/upload" else 1024 * 1024
        if path == "/api/guest/documents":
            # Its stricter streaming middleware remains responsible for ID uploads.
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = limit + 1
        response = JSONResponse({"detail": "Request is too large. Reduce the file size or number of items and try again."}, status_code=413)
        if declared < 0 or declared > limit:
            return await response(scope, receive, send)
        size = 0
        exceeded = False
        async def bounded_receive():
            nonlocal size, exceeded
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                exceeded = True
                raise HTTPException(413, "Request is too large")
            return message
        async def bounded_send(message):
            # Multipart parsers may translate receive errors to 400. Preserve 413.
            if not exceeded:
                await send(message)
        try:
            await self.app(scope, bounded_receive, bounded_send)
        except HTTPException:
            if not exceeded:
                raise
        if exceeded:
            await response(scope, receive, send)
