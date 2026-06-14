# Utils package for CXR processing
from .open_protected_xlsx import open_protected_xlsx


def __getattr__(name):
    if name == "ProcessCarpl":
        from .process_carpl import ProcessCarpl

        return ProcessCarpl
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["open_protected_xlsx", "ProcessCarpl"]
