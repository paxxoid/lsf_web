from ninja.errors import HttpError


def require_permission(request, permission: str) -> None:
    if not request.auth:
        raise HttpError(401, "Authentication required")

    if not request.auth.has_permission(permission):
        raise HttpError(
            403,
            f"API key lacks permission: {permission}",
        )