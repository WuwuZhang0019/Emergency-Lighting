"""Automatic default-power upgrades with real prior catalogs. Date: 2026-10-16.

Finite AutoLISP adapters and real files; native CAD acceptance remains pending.
"""
from pathlib import Path
import shutil
import tempfile
import unittest

from autolisp_host import Pair, Symbol, truth
import test_default_device_library as defaults
from test_diagram_store import dump

SOURCE = defaults.SOURCE


class DefaultPowerUpgradeTests(unittest.TestCase):
    setUp = defaults.DefaultDeviceLibraryTests.setUp
    call = defaults.DefaultDeviceLibraryTests.call
    get = defaults.DefaultDeviceLibraryTests.get
    put = defaults.DefaultDeviceLibraryTests.put
    entry = defaults.DefaultDeviceLibraryTests.entry
    fs = defaults.DefaultDeviceLibraryTests.fs
    binary = defaults.DefaultDeviceLibraryTests.binary
    prepare = defaults.DefaultDeviceLibraryTests.prepare

    def previous_library(self, folder, published=False, identity=None):
        root = self.prepare(folder)
        filename = 'published-power-source.eld' if published else 'legacy-defaults.eld'
        catalog = self.call('EL:DLParse', (SOURCE / filename).read_text(encoding='utf-8-sig'))
        self.assertTrue(truth(catalog))
        if identity or not published:
            catalog = self.put('library-id', identity or 'LIB-OLD-USER', catalog)
        shutil.copytree(SOURCE / 'assets', Path(folder, 'assets'))
        path = Path(folder, 'catalog.eld')
        path.write_text(dump(catalog), encoding='utf-8')
        copy = self.h.builtins['VL-FILE-COPY']

        def copy_history_only(source, destination):
            self.assertEqual(Path(source).name, 'catalog.eld', 'power upgrade recopied a graphic')
            return copy(source, destination)

        self.h.builtins['VL-FILE-COPY'] = copy_history_only
        self.h.builtins['GETFILED'] = lambda *a: self.fail('startup asked for manual import')
        self.h.builtins['EL:DLROOTSET'] = lambda *a: self.fail('startup switched the current library')
        self.h.builtins['EL:DLCAPTURESTART'] = lambda *a: self.fail('startup exported a legend')
        return root, path, catalog

    def row(self, catalog, identity):
        return self.call('EL:By', Symbol('DEVICE-ID'), identity, self.get('devices', catalog))

    def assert_power_defaults(self, snapshot):
        catalog = self.get('catalog', snapshot)
        rows = self.get('devices', catalog)
        self.assertEqual(len(rows), 49)
        self.assertEqual(sum(self.get('watts', r) == 1 for r in rows), 35)
        self.assertEqual(sum(self.get('watts', r) == 5 for r in rows), 11)
        for seed in self.get('devices', self.defaults):
            if self.get('watts', seed) is not None:
                for name in self.call('EL:DLEntryNames', seed):
                    resolved = self.call('EL:DLPowerEntry', name, snapshot)
                    self.assertEqual(self.get('watts', resolved), self.get('watts', seed))

    def test_blank_legacy_defaults_upgrade_at_load_without_import_or_graphic_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root, path, old = self.previous_library(folder)
            original = path.read_bytes()
            graphics = {p.relative_to(folder): (p.read_bytes(), p.stat().st_mtime_ns)
                        for p in Path(folder, 'assets').rglob('*') if p.is_file()}
            loaded = self.call('EL:DLDefaultStartup')
            self.assert_power_defaults(loaded)
            catalog = self.get('catalog', loaded)
            self.assertEqual(self.get('library-id', catalog), 'LIB-OLD-USER')
            self.assertEqual(self.get('revision', catalog), self.get('revision', old) + 1)
            self.assertEqual(self.h.lookup('*EL:DLROOT*'), root)
            self.assertEqual(Path(folder, 'history', str(self.get('revision', old)) + '.eld').read_bytes(), original)
            self.assertEqual(graphics, {p.relative_to(folder): (p.read_bytes(), p.stat().st_mtime_ns)
                                      for p in Path(folder, 'assets').rglob('*') if p.is_file()})
            before = path.read_bytes()
            self.h.builtins['EL:DLWRITETEXT'] = lambda *a: self.fail('repeated startup rewrote defaults')
            self.assertEqual(self.call('EL:DLDefaultStartup'), loaded)
            self.assertEqual(path.read_bytes(), before)

    def test_authors_export_upgrades_once_and_later_custom_power_and_disabling_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            root, path, old = self.previous_library(folder, published=True)
            loaded = self.call('EL:DLDefaultStartup')
            self.assert_power_defaults(loaded)
            catalog = self.get('catalog', loaded)
            self.assertEqual(self.get('library-id', catalog), self.get('library-id', old))
            for identity in ('ELDEV25', 'ELDEV42'):
                self.assertEqual(self.row(catalog, identity), self.row(old, identity))
            for identity, key, value in (('ELDEV2', 'watts', 9), ('ELDEV3', 'active', None)):
                row = self.put(key, value, self.row(catalog, identity))
                catalog = self.call('EL:DLUpsert', catalog, row)
                self.assertTrue(truth(self.call('EL:DLCommit', loaded, catalog)))
                loaded = self.call('EL:DLSnapshotLoad', root)
            original = path.read_bytes()
            self.h.builtins['EL:DLWRITETEXT'] = lambda *a: self.fail('startup reset a later user edit')
            # Reload is a separate user action; give it the adapter's normal step budget.
            self.h.steps = 0
            again = self.call('EL:DLDefaultStartup')
            self.assertEqual(self.get('catalog', again), catalog)
            self.assertEqual(path.read_bytes(), original)

    def test_existing_custom_values_zero_ground_names_deleted_and_revision_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            _, path, catalog = self.previous_library(folder)
            originals = {}
            changes = (
                ('ELDEV2', {'watts': 9, 'status': Symbol('READY'), 'active': True}),
                ('ELDEV3', {'revision': 2}),
                ('ELDEV4', {'watts': 0, 'zero-confirmed': True, 'status': Symbol('READY'), 'active': True}),
                ('ELDEV5', {'display': '本人修改的名称', 'aliases': ['个人别名']}),
                ('ELDEV6', {'status': Symbol('DELETED')}),
                ('ELDEV7', {'is-ground': True}),
            )
            rows = self.get('devices', catalog)
            for identity, fields in changes:
                old = self.row(catalog, identity)
                row = old
                for key, value in fields.items():
                    row = self.put(key, value, row)
                rows = [row if r == old else r for r in rows]
                originals[identity] = row
            catalog = self.put('devices', rows, catalog)
            path.write_text(dump(catalog), encoding='utf-8')
            loaded = self.call('EL:DLDefaultStartup')
            for identity, row in originals.items():
                self.assertEqual(self.row(self.get('catalog', loaded), identity), row)
            self.assertEqual(self.get('watts', self.row(self.get('catalog', loaded), 'ELDEV36')), 1)

    def test_published_saved_values_require_the_same_library_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            _, _, catalog = self.previous_library(folder, published=True, identity='LIB-OTHER-USER')
            row = self.row(catalog, 'ELDEV2')
            loaded = self.call('EL:DLDefaultStartup')
            self.assertEqual(self.row(self.get('catalog', loaded), 'ELDEV2'), row)

    def test_write_failure_and_concurrent_index_change_do_not_overwrite_user_library(self):
        for failure in ('write', 'concurrent_change'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                _, path, catalog = self.previous_library(folder)
                original = path.read_bytes()
                if failure == 'write':
                    self.h.builtins['EL:DLCOMMITLOCKED'] = lambda *a: None
                else:
                    acquire = self.h.builtins.get('EL:DLLOCKACQUIRE')
                    expected = dump(self.put('revision', self.get('revision', catalog) + 1, catalog)).encode('utf-8')
                    original = expected

                    def acquire_and_change(lock, owner):
                        if acquire:
                            acquired = acquire(lock, owner)
                        else:
                            self.h.builtins.pop('EL:DLLOCKACQUIRE', None)
                            try:
                                acquired = self.call('EL:DLLockAcquire', lock, owner)
                            finally:
                                self.h.builtins['EL:DLLOCKACQUIRE'] = acquire_and_change
                        path.write_bytes(expected)
                        return acquired

                    self.h.builtins['EL:DLLOCKACQUIRE'] = acquire_and_change
                self.call('EL:DLDefaultStartup')
                self.assertEqual(path.read_bytes(), original)
                self.assertIn('未完成', self.h.lookup('*EL:DLERROR*'))
                self.assertFalse(Path(folder, '.write-lock').exists())

    def test_pending_raw_power_is_not_upgraded_and_can_be_saved_after_other_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            root, _, catalog = self.previous_library(folder)
            snapshot = self.call('EL:DLSnapshotLoad', root)
            old = self.row(catalog, 'ELDEV49')
            self.h.set('*EL:DLUISTATE*', [Pair(Symbol('SNAPSHOT'), snapshot),
                Pair(Symbol('SELECTED'), 'ELDEV49'), Pair(Symbol('QUERY'), ''), [Symbol('DRAFTS')]])
            self.call('EL:DLUISetDraft', self.put('watts-text', '11', old))
            loaded = self.call('EL:DLDefaultStartup')
            self.assertEqual(self.row(self.get('catalog', loaded), 'ELDEV49'), old)
            self.call('EL:DLUIAdoptSnapshot', loaded)
            draft = self.call('EL:DLUIDraft')
            self.assertEqual(self.get('watts-text', draft), '11')
            converted = self.call('EL:DLUIToEntry', draft)
            candidate = self.call('EL:DLUpsert', self.get('catalog', loaded), converted)
            self.assertTrue(truth(candidate))


if __name__ == '__main__':
    unittest.main()
