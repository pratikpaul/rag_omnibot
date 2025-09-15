# omnibot/__init__.py
"""Omnibot package."""
__all__ = []

# Optional: lazy export
def __getattr__(name):
    if name == "build_graph_async":
        from .graph.graph_builder import build_graph_async
        return build_graph_async
    raise AttributeError(name)
