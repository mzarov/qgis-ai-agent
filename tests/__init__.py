import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import qgis.core  # noqa: F401
except ImportError:
    from tests import stub  # noqa: F401
