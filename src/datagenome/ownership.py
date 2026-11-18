from contextvars import ContextVar

# Trusted direct SDK calls have no HTTP owner context.
http_owner: ContextVar[str | None] = ContextVar("datagenome_owner", default=None)
