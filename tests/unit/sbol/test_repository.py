import sbol2

from buildcompiler.sbol.repository import PartShopRepositoryClient


class FakePartShop:
    def __init__(self):
        self.key = None
        self.login_calls = []
        self.pull_calls = []
        self._session_key = "session-key"

    def login(self, email, password):
        self.login_calls.append((email, password))

    def getKey(self):
        return self._session_key

    def pull(self, identity, document, recursive=True):
        self.pull_calls.append((identity, recursive))


def test_repository_client_anonymous_pull():
    doc = sbol2.Document()
    sbol2.setHomespace("https://example.org")
    component = sbol2.ComponentDefinition("component")
    doc.add(component)
    part_shop = FakePartShop()
    client = PartShopRepositoryClient(
        repository_url="https://example.org",
        document=doc,
        part_shop=part_shop,
    )

    identity = component.identity
    obj = client.pull_identity(identity)

    assert obj is not None
    assert part_shop.pull_calls == [(identity, True)]
    assert part_shop.login_calls == []


def test_repository_client_uses_auth_token_without_login():
    doc = sbol2.Document()
    part_shop = FakePartShop()
    client = PartShopRepositoryClient(
        repository_url="https://example.org",
        document=doc,
        auth_token="token-123",
        part_shop=part_shop,
    )

    assert part_shop.key == "token-123"
    assert client.auth_token == "token-123"
    assert part_shop.login_calls == []


def test_repository_client_logs_in_and_reuses_session_key():
    doc = sbol2.Document()
    part_shop = FakePartShop()
    client = PartShopRepositoryClient(
        repository_url="https://example.org",
        document=doc,
        email="user@example.org",
        password="secret",
        part_shop=part_shop,
    )

    assert part_shop.login_calls == [("user@example.org", "secret")]
    assert client.auth_token == "session-key"


def test_repository_client_repr_redacts_secrets():
    doc = sbol2.Document()
    part_shop = FakePartShop()
    client = PartShopRepositoryClient(
        repository_url="https://example.org",
        document=doc,
        auth_token="token-123",
        part_shop=part_shop,
    )

    rendered = repr(client)
    assert "token-123" not in rendered
    assert "secret" not in rendered
