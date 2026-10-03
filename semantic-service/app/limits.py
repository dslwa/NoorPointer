import json


class _TooLarge(Exception):
    pass


class BodySizeLimit:
    """ASGI middleware enforcing a request-body limit while the body is received, so an oversized upload is
    rejected up front (Content-Length) or cut off mid-stream (chunked), before multipart parsing spools it."""

    def __init__(self, app, limit: int, path_prefix: str) -> None:
        self.app = app
        self.limit = limit
        self.prefix = path_prefix

    async def _reject(self, send) -> None:
        body = json.dumps({"detail": f"request body larger than {self.limit} bytes"}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(self.prefix):
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and int(length) > self.limit:
            return await self._reject(send)

        received = 0
        exceeded = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    exceeded = True
                    raise _TooLarge()
            return message

        responded = False

        async def guarded_send(message):
            nonlocal responded
            if exceeded:  # the app turned our exception into its own error response: replace it with a 413
                if not responded:
                    responded = True
                    await self._reject(send)
                return
            responded = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _TooLarge:
            if not responded:
                await self._reject(send)
