import json


class _TooLarge(Exception):
    pass


class BodySizeLimit:
    """ASGI middleware enforcing a request-body limit while the body is received, so an oversized request
    is rejected up front (Content-Length) or cut off mid-stream (chunked), before any parsing or spooling.
    `limits` maps exact paths to their limit; every other path gets `default`."""

    def __init__(self, app, limits: dict[str, int], default: int) -> None:
        self.app = app
        self.limits = limits
        self.default = default

    @staticmethod
    async def _error(send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.limits.get(scope["path"].rstrip("/") or "/", self.default)
        too_large = f"request body larger than {limit} bytes"
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None:
            if not length.isdigit():
                return await self._error(send, 400, "invalid Content-Length")
            if int(length) > limit:
                return await self._error(send, 413, too_large)

        received = 0
        exceeded = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _TooLarge()
            return message

        responded = False

        async def guarded_send(message):
            nonlocal responded
            if exceeded:  # the app turned our exception into its own error response: replace it with a 413
                if not responded:
                    responded = True
                    await self._error(send, 413, too_large)
                return
            responded = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _TooLarge:
            if not responded:
                await self._error(send, 413, too_large)
