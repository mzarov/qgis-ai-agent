import importlib
import os
import pathlib
import sys
import tempfile
import unittest

import qgis
from qgis.core import Qgis, QgsApplication
from real_qgis_smoke import _build_and_extract, qgis_application


def main() -> int:
    """Run behavior tests against an installed ZIP in an isolated QGIS profile."""
    with tempfile.TemporaryDirectory(prefix="ai-agent-integration-") as temporary:
        root = pathlib.Path(temporary)
        package = _build_and_extract(root)
        sys.path.insert(0, os.fspath(package.parent))
        with qgis_application(root):
            for candidate in (
                pathlib.Path(QgsApplication.pkgDataPath()) / "python" / "plugins",
                pathlib.Path(qgis.__file__).resolve().parent.parent / "plugins",
            ):
                if candidate.is_dir():
                    sys.path.append(os.fspath(candidate))
            processing = importlib.import_module("processing.core.Processing")
            processing.Processing.initialize()
            installed = importlib.import_module("ai_agent")
            if pathlib.Path(installed.__file__).resolve().parent != package.resolve():
                raise RuntimeError("Integration tests must import the extracted plugin ZIP")
            suite = unittest.TestSuite(
                unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name))
                for name in ("real_qgis_cases", "real_qgis_network")
            )
            print(f"Installed-package workflows on QGIS {Qgis.QGIS_VERSION}", flush=True)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
