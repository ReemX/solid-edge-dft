"""Read Solid Edge draft (.dft) files: dimensions, styles, sheets, layers, text boxes."""
from .semantic import extract

__all__ = ["extract"]
