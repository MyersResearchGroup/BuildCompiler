"""Transient, token-only SynBioHub loading boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import sbol2

from buildcompiler.errors import (
    SynBioHubAuthenticationError,
    SynBioHubError,
    SynBioHubNetworkError,
    SynBioHubResourceError,
    SynBioHubResponseError,
)


def load_synbiohub_collections(
    collections: Iterable[str],
    *,
    sbh_registry: str,
    auth_token: str,
    document: sbol2.Document,
) -> None:
    """Load collections and their missing references without retaining credentials."""

    try:
        shop = sbol2.PartShop(sbh_registry)
        shop.key = auth_token
    except Exception as exc:
        raise _normalized_error(
            exc,
            operation="client initialization",
            identity="SynBioHub registry",
            secret=auth_token,
        ) from None
    try:
        for identity in sorted(set(collections)):
            _pull(shop, identity, document, operation="collection download")
        _hydrate_missing_references(shop, document)
    finally:
        # PartShop stores its authorization header value on ``key``. Keep the
        # client transient and erase that value before releasing it.
        shop.key = ""


def _hydrate_missing_references(shop: sbol2.PartShop, document: sbol2.Document) -> None:
    attempted: set[str] = set()
    while True:
        missing = sorted(
            identity
            for identity in _referenced_identities(document)
            if identity
            and document.find(identity) is None
            and identity not in attempted
        )
        if not missing:
            return
        for identity in missing:
            attempted.add(identity)
            _pull(shop, identity, document, operation="referenced identity download")


def _referenced_identities(document: sbol2.Document) -> set[str]:
    identities: set[str] = set()
    for collection in document.collections:
        identities.update(str(value) for value in collection.members)
    for implementation in document.implementations:
        identities.add(str(implementation.built))
    for component in document.componentDefinitions:
        identities.update(str(child.definition) for child in component.components)
        identities.update(str(value) for value in component.sequences)
    for module in document.moduleDefinitions:
        identities.update(str(item.definition) for item in module.functionalComponents)
        identities.update(str(item.definition) for item in module.modules)
    for derivation in document.combinatorialderivations:
        identities.add(str(derivation.masterTemplate))
        for variable in derivation.variableComponents:
            identities.update(str(value) for value in variable.variants)
            identities.update(str(value) for value in variable.variantCollections)
            identities.update(str(value) for value in variable.variantDerivations)
    return identities


def _pull(
    shop: sbol2.PartShop,
    identity: str,
    document: sbol2.Document,
    *,
    operation: str,
) -> None:
    try:
        shop.pull(identity, document)
    except Exception as exc:
        raise _normalized_error(
            exc,
            operation=operation,
            identity=identity,
            secret=shop.key,
        ) from None


def _normalized_error(
    exc: Exception, *, operation: str, identity: str, secret: str
) -> SynBioHubError:
    code = _sbol_error_code(exc)
    lowered = str(exc).lower()
    safe_resource = _safe_resource(identity, secret)
    if code == _error_code("SBOL_ERROR_HTTP_UNAUTHORIZED") or any(
        marker in lowered
        for marker in (
            "unauthorized",
            "invalid token",
            "expired token",
            "status code 401",
        )
    ):
        return SynBioHubAuthenticationError(
            f"SynBioHub authentication failed during {operation}; supply a valid token."
        )
    if code == _error_code("SBOL_ERROR_NOT_FOUND"):
        return SynBioHubResourceError(
            f"SynBioHub resource was not found during {operation}: {safe_resource}"
        )
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)) or any(
        marker in lowered
        for marker in ("connection", "network", "timed out", "timeout", "dns")
    ):
        return SynBioHubNetworkError(
            f"SynBioHub could not be reached during {operation}."
        )
    return SynBioHubResponseError(
        f"SynBioHub returned an unusable response during {operation}: {safe_resource}"
    )


def _sbol_error_code(exc: Exception) -> Any:
    if not isinstance(exc, sbol2.SBOLError):
        return None
    try:
        return exc.error_code()
    except Exception:
        return None


def _error_code(name: str) -> Any:
    return getattr(sbol2.SBOLErrorCode, name, object())


def _safe_resource(identity: str, secret: str) -> str:
    if secret and secret in identity:
        return "requested resource"
    try:
        parsed = urlsplit(identity)
    except ValueError:
        return identity if "token" not in identity.lower() else "requested resource"
    if not parsed.scheme:
        return identity if "token" not in identity.lower() else "requested resource"
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
