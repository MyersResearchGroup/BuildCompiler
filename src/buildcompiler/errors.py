"""Public, credential-safe BuildCompiler exception types."""


class BuildCompilerError(Exception):
    """Base class for clean BuildCompiler API errors."""


class SynBioHubError(BuildCompilerError):
    """Base class for normalized SynBioHub integration failures."""


class SynBioHubConfigurationError(SynBioHubError, ValueError):
    """The SynBioHub factory configuration is incomplete or invalid."""


class SynBioHubAuthenticationError(SynBioHubError):
    """SynBioHub rejected the supplied bearer token."""


class SynBioHubNetworkError(SynBioHubError):
    """SynBioHub could not be reached."""


class SynBioHubResourceError(SynBioHubError):
    """A requested SynBioHub resource could not be retrieved."""


class SynBioHubResponseError(SynBioHubError):
    """SynBioHub returned an unusable response."""
