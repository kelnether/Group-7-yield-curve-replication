"""Checks for the published input snapshot and fail-closed Route B behavior."""

import json
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from openpyxl import load_workbook

from boe_data import extract_panel, verified_payload
from run_route_b import EXPECTED_ROWS, SOURCE_DIR, publish_results, run_route_b, verify_release


class RouteBTests(unittest.TestCase):
    def test_required_cell_missing_stops_import(self):
        source = json.loads((SOURCE_DIR / "sources.json").read_text())["bank_of_england"]
        with ZipFile(SOURCE_DIR / source["archive"]) as archive:
            workbook = load_workbook(BytesIO(archive.read(source["workbook"])), data_only=True)
        try:
            workbook[source["sheet"]]["C5"] = None
            with self.assertRaisesRegex(ValueError, "required rate.*C5"):
                extract_panel(workbook, source)
        finally:
            workbook.close()

    def test_source_digest_rejects_changed_archive(self):
        source = json.loads((SOURCE_DIR / "sources.json").read_text())["bank_of_england"]
        with TemporaryDirectory() as temp:
            path = Path(temp) / source["archive"]
            path.write_bytes((SOURCE_DIR / source["archive"]).read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verified_payload(path, source["sha256"])

    def test_complete_release_and_changed_output(self):
        sources, tables = run_route_b(SOURCE_DIR)
        self.assertEqual({name: len(rows) for name, rows in tables.items()}, EXPECTED_ROWS)
        absent = [row for row in tables["coverage_audit.csv"] if row["status"] == "not_published"]
        self.assertEqual([row["as_of_date"][5:7] for row in absent], ["07", "08", "09", "10", "11", "12"])
        self.assertTrue(all(row["converged"] for row in tables["metrics.csv"]))
        with TemporaryDirectory() as temp:
            output = Path(temp) / "release"
            publish_results(output, sources, tables)
            publish_results(output, sources, tables)  # An identical release is idempotent.
            verify_release(output)
            metrics = output / "metrics.csv"
            metrics.write_bytes(metrics.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_release(output)
            with self.assertRaisesRegex(FileExistsError, "another release"):
                publish_results(output, sources, tables)
