
from buildcompiler.sbol import PartShopRepositoryClient


class FakePartShop:
    def __init__(self):
        self.key = None
        self.login_calls = []
        self.pull_calls = []

    def login(self, email, password):
        self.login_calls.append((email, password))
        self.key = "fake-session-token"

    def getKey(self):
        return self.key

    def pull(self, identity, document):
        self.pull_calls.append(identity)
        document.objects[identity] = {"identity": identity}


class FakeDocument:
    def __init__(self):
        self.objects = {}

    def find(self, identity):
        return self.objects.get(identity)


def test_repository_client_anonymous_pull():
    doc = FakeDocument()
    fake = FakePartShop()
    client = PartShopRepositoryClient("https://example.org", doc, part_shop=fake)

    resolved = client.pull_identity("https://example.org/ComponentDefinition/component/1")

    assert resolved is not None
    assert fake.login_calls == []


def test_repository_client_auth_token_does_not_login():
    doc = FakeDocument()
    fake = FakePartShop()
    client = PartShopRepositoryClient(
        "https://example.org", doc, auth_token="token", part_shop=fake
    )

    assert client.auth_token == "token"
    assert fake.key == "token"
    assert fake.login_calls == []
    assert "token" not in repr(client)


def test_repository_client_email_password_login_and_key_reuse():
    doc = FakeDocument()
    fake = FakePartShop()
    client = PartShopRepositoryClient(
        "https://example.org",
        doc,
        email="user@example.org",
        password="secret",
        part_shop=fake,
    )

    client.pull_identity("https://example.org/ComponentDefinition/component/1")

    assert fake.login_calls == [("user@example.org", "secret")]
    assert client.auth_token == "fake-session-token"
    assert fake.pull_calls == ["https://example.org/ComponentDefinition/component/1"]
