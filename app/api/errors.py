from fastapi import HTTPException

_AUTH_HINTS = (
    "twoColumnBrowseResultsRenderer",
    "signInEndpoint",
    "Sign in to listen",
)


def explain(exc: Exception, service: str) -> HTTPException:
    text = str(exc)

    if any(hint in text for hint in _AUTH_HINTS):
        return HTTPException(401, f"{service}: token expired or invalid, paste a fresh one")

    if "Unauthorized" in text or "unauthorized" in text or "401" in text[:200]:
        return HTTPException(401, f"{service}: token rejected by the service")

    if "Network" in text or "ConnectionError" in type(exc).__name__:
        return HTTPException(502, f"{service}: cannot reach the service ({type(exc).__name__})")

    return HTTPException(502, f"{service}: {type(exc).__name__}: {text[:300]}")
