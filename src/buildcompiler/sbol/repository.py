"""SynBioHub repository adapter backed by ``sbol2.PartShop``."""

from __future__ import annotations

from typing import Any

import sbol2


class PartShopRepositoryClient:
    """Authenticated/anonymous repository pull client.

    Secrets are intentionally not exposed in ``repr``.
    """

    def __init__(
        self,
        repository_url: str,
        document: sbol2.Document,
        *,
        auth_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        part_shop: sbol2.PartShop | None = None,
    ) -> None:
        if not repository_url:
            raise ValueError("repository_url is required")
        if auth_token and (email or password):
            raise ValueError("Provide either auth_token or email/password, not both")
        if (email and not password) or (password and not email):
            raise ValueError("Both email and password are required together")

        self.repository_url = repository_url
        self.document = document
        self.part_shop = part_shop or sbol2.PartShop(repository_url)
        self._auth_token: str | None = None

        if auth_token:
            self.part_shop.key = auth_token
            self._auth_token = auth_token
        elif email and password:
            self.part_shop.login(email, password)
            self._auth_token = self.part_shop.getKey()

    @property
    def auth_token(self) -> str | None:
        return self._auth_token

    def pull_identity(self, identity: str) -> Any | None:
        self.part_shop.pull(identity, self.document)
        return self.document.find(identity)

    def pull_collection(self, collection_uri: str) -> None:
        self.part_shop.pull(collection_uri, self.document)

    def __repr__(self) -> str:
        return (
            "PartShopRepositoryClient("
            f"repository_url={self.repository_url!r}, has_auth={self._auth_token is not None})"
        )
