"""Continuous editing with real catalogs and a DCL list adapter. Date: 2026-10-15.

The adapter models indexed replacement and rebuild scroll resets, not native CAD.
"""
from pathlib import Path
import os
import tempfile
import unittest

from autolisp_host import truth
from test_diagram_store import dump
from test_device_assets import AUTODESK_VECTOR_SLIDE
import test_library_autosave as autosave


class LibraryEditFlowTests(unittest.TestCase):
    setUp = autosave.LibraryAutosaveTests.setUp
    call = autosave.LibraryAutosaveTests.call
    get = autosave.LibraryAutosaveTests.get
    put = autosave.LibraryAutosaveTests.put
    entry = autosave.LibraryAutosaveTests.entry
    fs = autosave.LibraryAutosaveTests.fs
    rows = autosave.LibraryAutosaveTests.rows
    edit = autosave.LibraryAutosaveTests.edit

    def editor(self, folder, count=2):
        autosave.LibraryAutosaveTests.editor(self, folder)
        for index in range(2, count):
            self.cat = self.call('EL:DLUpsert', self.cat, self.entry(f'Lamp {index}'))
        self.path.write_text(dump(self.cat), encoding='utf-8')
        state = self.h.lookup('*EL:DLUISTATE*')
        self.h.set('*EL:DLUISTATE*', self.put('snapshot',
            self.call('EL:DLSnapshotLoad', str(self.path.parent).replace('\\', '/') + '/'), state))
        self.labels, self.list_calls, self.top = [], [], 0
        def start(key, operation=3, index=0):
            self.assertEqual(key, 'dl_rows')
            self.list_calls.append((operation, index))
            self.operation, self.index = operation, index
            if operation == 3:
                self.labels.clear()
                self.top = 0
        def add(text):
            if self.operation == 1:
                self.labels[self.index] = text
            else:
                self.labels.append(text)
        self.h.builtins.update({'START_LIST': start, 'ADD_LIST': add})
        self.call('EL:DLUIFill')
        self.list_calls.clear()

    def select(self, index):
        # Native list selection changes first, then its action reports that index.
        self.tiles['dl_rows'] = str(index)
        self.call('EL:DLUISelect', str(index))
        state = self.h.lookup('*EL:DLUISTATE*')
        self.assertEqual(self.get('selected', state), f'ELDEV{index + 1}')
        self.assertEqual(self.tiles['dl_block'], self.get('block-name', self.call('EL:DLUIEntry')))

    def assets(self):
        self.reads = []
        for name in ('EL:DLLegend', 'EL:DLUIAssetReady'):
            self.h.builtins.pop(name.upper(), None)
        self.h.builtins['VL-FILE-SYSTIME'] = lambda p: [Path(p).stat().st_mtime_ns]
        def read(path, count):
            self.reads.append((Path(path).name, count))
            raw = Path(path).read_bytes()
            return list(raw if count == -1 else raw[:count])
        self.h.builtins['EL:DLBYTES'] = read
        snapshot = self.get('snapshot', self.h.lookup('*EL:DLUISTATE*'))
        for row in self.get('devices', self.get('catalog', snapshot)):
            folder = self.path.parent / self.get('block-file', row)
            folder.parent.mkdir(parents=True, exist_ok=True)
            folder.write_bytes(b'AC1024fixture')
            slide = self.path.parent / self.get('legend-file', row)
            slide.write_bytes(AUTODESK_VECTOR_SLIDE)
            row = self.put('legend-size', [573, 293], row)
            row = self.put('legend-checksum', self.call('EL:DLChecksum', str(slide)), row)
            self.cat = self.call('EL:DLUpsert', self.cat, row)
        self.path.write_text(dump(self.cat), encoding='utf-8')
        self.h.set('*EL:DLUISTATE*', self.put('snapshot',
            self.call('EL:DLSnapshotLoad', self.get('root', snapshot)), self.h.lookup('*EL:DLUISTATE*')))
        self.call('EL:DLUIFill')
        self.reads.clear()
        self.list_calls.clear()

    def test_focus_loss_then_rapid_selection_preserves_scrolled_indices_and_each_power(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder, 25)
            self.top = 10
            self.select(12)
            for index, target in ((12, 13), (13, 20), (20, 14), (14, 15)):
                self.assertTrue(truth(self.edit('dl_watts', str(100 + index))))
                self.select(target)
                self.assertEqual(self.tiles['dl_rows'], str(target))
                self.assertEqual(self.top, 10)
            rows = self.rows()
            for index in (12, 13, 20, 14):
                self.assertEqual(self.get('watts', rows[index]), 100 + index)
            self.assertEqual(self.get('watts', rows[15]), 5)
            self.assertEqual(self.list_calls, [])

    def test_rename_replaces_only_that_row_without_moving_a_filtered_list(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder, 25)
            self.call('EL:DLUIQuery', 'Lamp', None)
            self.top = 10
            self.select(12)
            self.list_calls.clear()
            self.edit('dl_block', 'Other name')
            self.edit('dl_display', '新设备名')
            self.assertIn('Other name / 新设备名', self.labels[12])
            self.assertEqual(self.top, 10)
            self.assertEqual(len(self.labels), 25)
            self.assertEqual(self.list_calls, [(1, 12), (1, 12)])
            self.select(13)
            self.assertEqual(self.tiles['dl_block'], 'Lamp 13')

    def test_parameters_reuse_validated_assets_and_switching_back_does_not_reread_them(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            self.assets()
            self.assertTrue(truth(self.edit('dl_watts', '17')))
            self.assertEqual(self.reads, [])
            self.select(1)
            self.assertCountEqual(self.reads, [('legend.sld', 31), ('legend.sld', -1), ('block.dwg', 6)])
            self.reads.clear()
            self.edit('dl_watts', '18')
            self.select(0)
            self.assertEqual(self.reads, [])
            self.assertEqual([self.get('watts', row) for row in self.rows()], [17, 18])

    def test_changed_or_missing_asset_invalidates_the_editor_proof_and_keeps_input(self):
        for missing, same_size in ((True, False), (False, False), (False, True)):
            with self.subTest(missing=missing, same_size=same_size), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                self.editor(folder)
                self.assets()
                original = self.path.read_bytes()
                row = self.call('EL:DLUIEntry')
                slide = self.path.parent / self.get('legend-file', row)
                if missing:
                    slide.unlink()
                else:
                    stamp = slide.stat().st_mtime_ns
                    data = slide.read_bytes()
                    slide.write_bytes(data[:-1] + bytes([data[-1] ^ 1]) if same_size else b'bad')
                    os.utime(slide, ns=(stamp + 2_000_000_000, stamp + 2_000_000_000))
                self.assertFalse(truth(self.edit('dl_watts', '19')))
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(self.get('watts-text', self.call('EL:DLUIDraft')), '19')

    def test_explicit_refresh_revalidates_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            self.assets()
            self.call('EL:DLUIRefresh')
            self.assertCountEqual(self.reads, [('legend.sld', 31), ('legend.sld', -1), ('block.dwg', 6)])

    def test_parameter_commit_keeps_locked_checks_and_uses_the_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            reads = []
            def read(path):
                reads.append(Path(path))
                return Path(path).read_text(encoding='utf-8')
            self.h.builtins['EL:DLREADTEXT'] = read
            self.h.builtins['EL:DLSNAPSHOTLOAD'] = lambda *args: self.fail('redundant catalog reload')
            self.assertTrue(truth(self.edit('dl_watts', '21')))
            self.assertEqual(reads.count(self.path), 2)  # Locked original plus published readback.
            snapshot = self.get('snapshot', self.h.lookup('*EL:DLUISTATE*'))
            self.assertEqual(self.get('raw', snapshot), self.path.read_text(encoding='utf-8'))
            self.path.write_text(self.path.read_text(encoding='utf-8') + '\n', encoding='utf-8')
            external = self.path.read_bytes()
            self.assertFalse(truth(self.edit('dl_watts', '22')))
            self.assertEqual(self.path.read_bytes(), external)
            self.assertEqual(self.get('watts-text', self.call('EL:DLUIDraft')), '22')


if __name__ == '__main__':
    unittest.main()
