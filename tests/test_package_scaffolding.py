"""Import smoke tests for clean-architecture package scaffolding."""


def test_clean_architecture_package_imports() -> None:
    import buildcompiler.api  # noqa: F401
    import buildcompiler.domain  # noqa: F401
    import buildcompiler.planning  # noqa: F401
    import buildcompiler.execution  # noqa: F401
    import buildcompiler.stages  # noqa: F401
    import buildcompiler.sbol  # noqa: F401
    import buildcompiler.inventory  # noqa: F401
    import buildcompiler.adapters  # noqa: F401
    import buildcompiler.adapters.pudu  # noqa: F401
    import buildcompiler.adapters.opentrons  # noqa: F401
    import buildcompiler.reporting  # noqa: F401
