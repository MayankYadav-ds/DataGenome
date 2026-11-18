from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimit(Exception):
    pass


class PlatformBodyLimit:
    """Bound JSON parsing for the new platform routes as well as chunked requests."""

    def __init__(self, app: ASGIApp, maximum: int = 6_000_000) -> None:
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        lengths = [
            value for key, value in scope.get("headers", []) if key == b"content-length"
        ]
        if lengths:
            try:
                too_large = int(lengths[0]) > self.maximum
            except ValueError:
                too_large = True
            if too_large:
                await JSONResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "Request exceeds the byte budget.",
                        }
                    },
                    status_code=413,
                )(scope, receive, send)
                return
        size = 0

        async def limited() -> Message:
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.maximum:
                    raise BodyLimit
            return message

        try:
            await self.app(scope, limited, send)
        except BodyLimit:
            await JSONResponse(
                {
                    "error": {
                        "code": "request_too_large",
                        "message": "Request exceeds the byte budget.",
                    }
                },
                status_code=413,
            )(scope, receive, send)
