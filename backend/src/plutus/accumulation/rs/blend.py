"""Backwards-compat re-export from the canonical shared location.

The implementation lives in ``plutus.shared.rs.blend`` so that ``plutus.swing``
can also import it without violating the swing-accumulation independence rule.
"""

from plutus.shared.rs.blend import RSBlend, RSBlendResult

__all__ = ["RSBlend", "RSBlendResult"]
