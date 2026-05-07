"""SynBioHub repository client adapters."""

from __future__ import annotations

from typing import Any

import sbol2


class PartShopRepositoryClient:
    """Thin adapter around ``sbol2.PartShop`` for identity-based pulls."""

    def __init__(
        self,
        repository_url: str,
        document: sbol2.Document,
        auth_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        part_shop: Any | None = None,
    ) -> None:
        if not repository_url:
            raise ValueError("repository_url is required")
        if auth_token and (email or password):
            raise ValueError(
                "Specify either auth_token or email/password credentials, not both."
            )
        if (email and not password) or (password and not email):
            raise ValueError("Both email and password are required for login.")

        self.repository_url = repository_url
        self.document = document
        self._auth_token: str | None = None
        self.part_shop = part_shop or sbol2.PartShop(repository_url)

        if auth_token is not None:
            self.part_shop.key = auth_token
            self._auth_token = auth_token
        elif email and password:
            self.part_shop.login(email, password)
            self._auth_token = self.part_shop.getKey()

    @property
    def auth_token(self) -> str | None:
        return self._auth_token

    def pull_identity(self, identity: str) -> object | None:
        self.part_shop.pull(identity, self.document, recursive=True)
        return self.document.find(identity)

    def __repr__(self) -> str:
        token_state = "set" if self._auth_token else "unset"
        return (
            "PartShopRepositoryClient("
            f"repository_url={self.repository_url!r}, auth_token={token_state})"
        )
