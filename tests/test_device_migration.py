"""Legacy migration is explicit and preserves originals. Date: 2026-10-11."""
from pathlib import Path
import tempfile
import unittest

import test_device_library as backend
from autolisp_host import Pair, Symbol, truth
from test_diagram_store import dump


class DeviceMigrationTests(unittest.TestCase):
    setUp = backend.DeviceLibraryTests.setUp
    call = backend.DeviceLibraryTests.call
    get = backend.DeviceLibraryTests.get
    put = backend.DeviceLibraryTests.put
    entry = backend.DeviceLibraryTests.entry
    fs = backend.DeviceLibraryTests.fs

    def state(self):
        state = self.h.run("'((query . \"\") (drafts) (selected))")
        self.h.set('*EL:DLUISTATE*', self.put('snapshot', [Pair(Symbol('CATALOG'), self.cat)], state))

    def candidates(self, powers=(('Lamp', 5),)):
        return self.call('EL:DLImportCandidates', [Pair(k, v) for k, v in powers], None)

    def test_import_preserves_zero_without_inventing_ground_or_assets(self):
        self.state()
        rows = self.candidates((('Lamp', 0), ('Exit', 1)))
        self.assertEqual(self.call('EL:DLImportDrafts', rows), 2)
        drafts = self.get('drafts', self.h.lookup('*EL:DLUISTATE*'))
        entries=[self.call('cdr', p) for p in drafts]
        self.assertEqual(len({self.get('device-id', row) for row in entries}), 2)
        lamp = next(row for row in entries if self.get('block-name', row) == 'Lamp')
        self.assertEqual(self.get('watts', lamp), 0)
        self.assertFalse(truth(self.get('zero-confirmed', lamp)))
        self.assertFalse(truth(self.get('ground-confirmed', lamp)))
        self.assertFalse(truth(self.get('active', lamp)))
        self.assertEqual(self.get('asset-revision', lamp), 0)
        self.assertEqual(self.get('revision', self.cat), 0)

    def test_same_name_different_params_requires_explicit_choice_without_partial_drafts(self):
        self.state()
        rows = self.candidates((('Lamp', 5), ('LAMP', 7)))
        self.assertTrue(truth(self.call('EL:DLImportConflict', rows[0], rows)))
        original = self.h.lookup('*EL:DLUISTATE*')
        with self.assertRaises(RuntimeError): self.call('EL:DLImportDrafts', rows)
        self.assertEqual(self.h.lookup('*EL:DLUISTATE*'), original)
        self.assertEqual(self.call('EL:DLImportDrafts', rows[1:]), 1)
        self.assertEqual(self.get('watts', self.call('EL:DLUIEntry')), 7)

    def test_identical_items_deduplicate_but_display_conflicts_remain(self):
        records = self.h.run("'(((identity \"Lamp\" nil \"old\") (category . lighting) (display . \"Lamp\") (watts . 5) (zero-confirmed)))")
        rows = self.call('EL:DLImportCandidates', [Pair('Lamp', 5)], records)
        self.assertEqual(len(rows), 1)
        records[0] = self.put('display', '不同设备名', records[0])
        rows = self.call('EL:DLImportCandidates', [Pair('Lamp', 5)], records)
        self.assertEqual(len(rows), 2)

    def test_existing_primary_or_alias_is_never_overwritten(self):
        self.cat = self.call('EL:DLUpsert', self.cat, self.put('aliases', ['Old Lamp'], self.entry('Lamp')))
        self.state()
        with self.assertRaises(RuntimeError): self.call('EL:DLImportDrafts', self.candidates((('Old Lamp', 9),)))
        self.assertFalse(truth(self.get('drafts', self.h.lookup('*EL:DLUISTATE*'))))

    def test_validated_legacy_files_are_backed_up_with_exact_original_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fs(d)
            self.h.builtins.update({'VL-FILE-SIZE': lambda p: Path(p).stat().st_size,
                'VL-FILENAME-BASE': lambda p: Path(p).stem,
                'EL:READDATA': lambda p: self.call('EL:StoreParse', Path(p).read_text(encoding='utf-8')),
                'EL:DLFOLDERCLAIM': lambda p: Path(p).mkdir() or True,
                'EL:DLFILESEQUAL': lambda a, b: Path(a).read_bytes() == Path(b).read_bytes()})
            source = Path(d, 'block-powers.eld')
            data = self.h.run("'((version . 1) (powers (\"应急灯\" . 5)))")
            source.write_text(dump(data), encoding='utf-8')
            original = source.read_bytes()
            self.assertEqual(len(self.call('EL:DLLegacyRead', [str(source)])), 1)
            backup = self.call('EL:DLLegacyBackup', [Pair(Symbol('ROOT'), root)], [str(source)])
            self.assertEqual(Path(backup, source.name).read_bytes(), original)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(Path(d, 'catalog.eld').exists())
            source.write_text('(version . 99)', encoding='utf-8')
            with self.assertRaises(RuntimeError): self.call('EL:DLLegacyRead', [str(source)])
            self.assertEqual(source.read_text(), '(version . 99)')


if __name__ == '__main__': unittest.main()
