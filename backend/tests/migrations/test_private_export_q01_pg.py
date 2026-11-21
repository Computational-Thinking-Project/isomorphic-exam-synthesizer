"""Historical Q01 rows -> real approval/RPC020/source ZIP; PDF and Storage are doubles.

Golden math's pre-existing TASK-306 conversion failure is tracked separately;
the unchanged content still exercises DB authorization, manifest and replay here.
"""

from io import BytesIO
from zipfile import ZipFile

import test_export_q01_pg as q01
import test_private_export_pg as private_pg
from test_export_snapshot_pg import OWNER, ExportSnapshotPostgresFixture, SqlReadClient

from app.services.exporter.bundle_builder import build_bundle, required_pdf_names
from app.services.exporter.manifest_bundle import with_manifest
from app.services.exporter.private_repository import SupabaseExportLedger
from app.services.exporter.private_service import PrivateExportService, user_snapshot_loader


class PrivateQ01PostgresTests(ExportSnapshotPostgresFixture):
    seed = q01.ExportQ01PostgresTests.seed
    command = private_pg.PrivateExportPostgresTests.command

    def check_private_bundle(self):
        self.approve()
        store = private_pg.BlobStore()
        builds = []

        def build(snapshot):
            builds.append(snapshot)
            assert all(q.solution_md == "" for v in snapshot.versions for q in v.questions)
            return with_manifest(
                snapshot,
                build_bundle(
                    snapshot, {name: b"%PDF-1.4\n%%EOF\n" for name in required_pdf_names(snapshot)}
                ),
            )

        service = PrivateExportService(
            user_snapshot_loader(
                SqlReadClient(self), provenance_db=SqlReadClient(self, role="service_role")
            ),
            SupabaseExportLedger(private_pg.RpcClient(self)),
            store,
            build=build,
        )
        first = service.export(self.sid, OWNER)
        assert first.state == "ready"
        assert service.export(self.sid, OWNER) == first
        assert service.status(self.sid, OWNER) == first
        assert store.uploads == len(builds) == 1
        service.download(self.sid, OWNER)
        assert (
            self.sql(f"SELECT status FROM exam_sessions WHERE id='{self.sid}'").stdout.strip()
            == "exported"
        )
        with ZipFile(BytesIO(store.objects[first.artifact.object_path])) as archive:
            assert archive.testzip() is None
            for path in archive.namelist():
                if path.endswith(".pdf"):
                    assert archive.read(path).startswith(b"%PDF-")

    def test_fallback_empty_private_export_replay(self):
        self.check_private_bundle()

    def test_clone_empty_private_export_replay(self):
        self.check_private_bundle()
