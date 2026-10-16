"""Complete library transfer with real files. Date: 2026-10-16. Native CAD pending."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Pair, Symbol, truth
from test_diagram_store import dump
import test_device_assets as assets
import test_library_location as location


class LibraryTransferTests(unittest.TestCase):
    setUp = assets.DeviceAssetsTests.setUp
    call = assets.DeviceAssetsTests.call
    get = assets.DeviceAssetsTests.get
    put = assets.DeviceAssetsTests.put
    entry = assets.DeviceAssetsTests.entry
    fs = assets.DeviceAssetsTests.fs
    binary = assets.DeviceAssetsTests.binary
    slide = assets.DeviceAssetsTests.slide

    def library(self, folder):
        self.parent = Path(folder)
        self.root = self.fs(self.parent / 'source')
        Path(self.root).mkdir()
        self.binary()
        for name, watts in (('备用照明', 5), ('地面疏散灯', 0)):
            row = self.entry(name, watts, ground=watts == 0)
            dwg = Path(self.root, self.get('block-file', row))
            dwg.parent.mkdir(parents=True)
            dwg.write_bytes(b'AC1024' + name.encode('utf-8'))
            slide = Path(self.root, self.get('legend-file', row))
            slide.write_bytes(self.slide())
            row = self.put('legend-checksum', self.call('EL:DLChecksum', str(slide)), row)
            self.cat = self.call('EL:DLUpsert', self.cat, row)
        self.cat = self.call('EL:DLDelete', self.cat, 'ELDEV2')
        self.cat = self.call('EL:DLUpsert', self.cat, self.entry('待补图形', watts=None, ready=False))
        self.path = Path(self.root, 'catalog.eld')
        self.path.write_text(dump(self.cat), encoding='utf-8')
        Path(self.root, 'recognition-preset.eld').write_bytes(b'preset-fixture')
        snapshot = self.call('EL:DLTransferRead', str(self.path))
        self.h.set('*EL:DLUISTATE*', [Pair(Symbol('SNAPSHOT'), snapshot),
            Pair(Symbol('QUERY'), '原来的搜索'), Pair(Symbol('SELECTED'), 'ELDEV1'), [Symbol('DRAFTS')]])
        self.h.set('*EL:DLROOT*', self.root)
        self.export_base = self.parent / 'export'
        self.export_base.mkdir()
        self.h.builtins['EL:DLTRANSFERFOLDER'] = lambda: str(self.export_base) + '/'
        self.h.builtins['EL:DLDEFAULTROOT'] = lambda: str(self.parent / 'user') + '/'
        self.registry = []
        self.h.builtins['VL-REGISTRY-WRITE'] = lambda *args: self.registry.append(args) or True
        self.h.builtins['STARTAPP'] = lambda *args: True
        self.h.builtins['VL-STRING-TRANSLATE'] = lambda a, b, value: value.translate(str.maketrans(a, b))
        self.h.builtins['GETFILED'] = lambda *args: None
        return snapshot

    def test_export_and_import_preserve_parameters_graphics_deleted_and_blank_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            original = self.library(folder)
            state = self.h.lookup('*EL:DLUISTATE*')
            raw = self.path.read_bytes()
            exported = self.call('EL:DLLibraryTransferUI', True)
            self.assertTrue(truth(exported))
            self.assertEqual(self.h.lookup('*EL:DLUISTATE*'), state)
            self.assertEqual(Path(exported, 'catalog.eld').read_bytes(), raw)
            for row in self.get('devices', self.cat):
                if self.get('asset-revision', row):
                    for key in ('block-file', 'legend-file'):
                        relative = self.get(key, row)
                        self.assertEqual(Path(exported, relative).read_bytes(), Path(self.root, relative).read_bytes())
            self.assertEqual(Path(exported, 'recognition-preset.eld').read_bytes(), b'preset-fixture')
            self.h.builtins['GETFILED'] = lambda *args: str(Path(exported, 'catalog.eld'))
            imported = self.call('EL:DLLibraryTransferUI', None)
            self.assertTrue(truth(imported))
            self.assertEqual(self.get('catalog', imported), self.get('catalog', original))
            imported_root = Path(self.get('root', imported))
            self.assertNotEqual(imported_root, Path(self.root))
            self.assertNotEqual(imported_root, Path(exported))
            self.assertEqual(Path(imported_root, 'catalog.eld').read_bytes(), raw)
            self.assertEqual(self.path.read_bytes(), raw)
            self.assertEqual(self.get('root', self.get('snapshot', self.h.lookup('*EL:DLUISTATE*'))),
                             self.get('root', imported))
            self.assertEqual(self.call('EL:Get', self.get('root', original), self.h.lookup('*EL:DLUIDIRECTORIES*')), state)
            self.assertEqual(len(self.registry), 1)

    def test_cancel_does_not_change_library_or_write_files(self):
        with tempfile.TemporaryDirectory() as folder:
            self.library(folder)
            state = self.h.lookup('*EL:DLUISTATE*')
            self.h.builtins['EL:DLTRANSFERFOLDER'] = lambda: None
            self.assertIsNone(self.call('EL:DLLibraryTransferUI', True))
            self.assertIsNone(self.call('EL:DLLibraryTransferUI', None))
            self.assertEqual(self.h.lookup('*EL:DLUISTATE*'), state)
            self.assertEqual(list(self.export_base.iterdir()), [])
            self.assertEqual(self.registry, [])

    def test_copy_failure_never_publishes_a_catalog_or_changes_the_source(self):
        with tempfile.TemporaryDirectory() as folder:
            self.library(folder)
            raw = self.path.read_bytes()
            self.h.builtins['VL-FILE-COPY'] = lambda *args: None
            self.assertFalse(truth(self.call('EL:DLLibraryTransferUI', True)))
            self.assertEqual(list(self.export_base.rglob('catalog.eld')), [])
            self.assertEqual(self.path.read_bytes(), raw)
            self.assertIn('未完成', self.h.lookup('*EL:DLERROR*'))

    def test_invalid_missing_or_corrupt_assets_and_conflicts_do_not_switch_library(self):
        for failure in ('invalid', 'missing', 'corrupt', 'changed', 'locked', 'registry'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                self.library(folder)
                state = self.h.lookup('*EL:DLUISTATE*')
                self.h.builtins['GETFILED'] = lambda *args: str(self.path)
                if failure == 'invalid':
                    self.path.write_text('(not-a-library)', encoding='utf-8')
                elif failure in ('missing', 'corrupt'):
                    row = self.get('devices', self.cat)[0]
                    slide = Path(self.root, self.get('legend-file', row))
                    if failure == 'missing':
                        slide.unlink()
                    else:
                        slide.write_bytes(b'bad slide')
                elif failure == 'changed':
                    copier = self.h.builtins['VL-FILE-COPY']
                    def copy(a, b):
                        result = copier(a, b)
                        self.path.write_text(dump(self.cat) + '\n', encoding='utf-8')
                        return result
                    self.h.builtins['VL-FILE-COPY'] = copy
                elif failure == 'locked':
                    Path(self.root, '.write-lock').write_text('other-writer', encoding='ascii')
                else:
                    self.h.builtins['VL-REGISTRY-WRITE'] = lambda *args: None
                self.assertFalse(truth(self.call('EL:DLLibraryTransferUI', None)))
                self.assertEqual(self.h.lookup('*EL:DLUISTATE*'), state)
                self.assertEqual(self.h.lookup('*EL:DLROOT*'), self.root)

    def test_export_collision_never_overwrites_an_existing_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            self.library(folder)
            target = self.call('EL:DLLibraryTransferUI', True)
            raw = Path(target, 'catalog.eld').read_bytes()
            self.assertFalse(truth(self.call('EL:DLLibraryTransferUI', True)))
            self.assertEqual(Path(target, 'catalog.eld').read_bytes(), raw)

    def test_native_folder_picker_arguments_release_and_cancel_contract(self):
        for outcome in ('selected', 'cancelled', 'error'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                self.library(folder)
                self.h.builtins.pop('EL:DLTRANSFERFOLDER')
                calls, released = [], []
                shell, selected, item = object(), object(), object()
                self.h.builtins['VLAX-CREATE-OBJECT'] = lambda name: shell
                def invoke(obj, method, *args):
                    calls.append((obj, str(method), args))
                    if outcome == 'error':
                        raise OSError('folder picker unavailable')
                    return selected if outcome == 'selected' else None
                self.h.builtins['VLAX-INVOKE-METHOD'] = invoke
                self.h.builtins['VLAX-GET-PROPERTY'] = lambda obj, key: item if str(key) == 'SELF' else str(self.export_base)
                self.h.builtins['VLAX-RELEASE-OBJECT'] = lambda obj: released.append(obj)
                result = self.call('EL:DLTransferFolder')
                self.assertEqual(calls, [(shell, 'BROWSEFORFOLDER', (0, '选择导出设备库的保存位置', 65))])
                if outcome == 'selected':
                    self.assertEqual(result, str(self.export_base) + '/')
                    self.assertEqual(released, [item, selected, shell])
                else:
                    self.assertIsNone(result)
                    self.assertEqual(released, [shell])


class LibraryTransferDialogTests(unittest.TestCase):
    fixture = location.LibraryLocationDialogTests.fixture

    def test_main_panel_buttons_save_before_transfer_and_return_to_same_flow(self):
        for key, exporting in (('dl_import', False), ('dl_export', True)):
            with self.subTest(key=key):
                f, callbacks, _ = self.fixture()
                transfers = []
                def transfer(value):
                    row = f.get('devices', f.call('EL:DLParse', self.catalog_path.read_text(encoding='utf-8')))[0]
                    transfers.append((bool(value), f.get('watts', row)))
                f.h.builtins['EL:DLLIBRARYTRANSFERUI'] = transfer
                f.h.builtins['EL:DLCAPTUREFILE'] = lambda *args: self.fail('repair callback still bound')
                def choose():
                    f.tiles['dl_watts'] = '17'
                    f.invoke_action(callbacks, key)
                f.actions = [choose, lambda: f.invoke_action(callbacks, 'cancel')]
                f.dialog()
                self.assertEqual(transfers, [(exporting, 17)])
                self.assertEqual(f.dialogs, ['el_panel', 'el_panel'])
                self.assertNotIn('dl_repair', callbacks)

    def test_standalone_buttons_save_before_transfer_and_return_to_same_editor(self):
        for key, exporting in (('dl_import', False), ('dl_export', True)):
            with self.subTest(key=key):
                f, callbacks, _ = self.fixture()
                f.call('EL:DLUIPanelBegin', f.call('EL:DLSnapshot'))
                transfers = []
                def transfer(value):
                    row = f.get('devices', f.call('EL:DLParse', self.catalog_path.read_text(encoding='utf-8')))[0]
                    transfers.append((bool(value), f.get('watts', row)))
                f.h.builtins['EL:DLLIBRARYTRANSFERUI'] = transfer
                f.h.builtins['EL:DLCAPTUREFILE'] = lambda *args: self.fail('repair callback still bound')
                def choose():
                    f.tiles['dl_watts'] = '1'
                    f.invoke_action(callbacks, key)
                f.actions = [choose, lambda: f.invoke_action(callbacks, 'dl_close')]
                f.call('EL:DLUIRun')
                self.assertEqual(transfers, [(exporting, 1)])
                self.assertEqual(f.dialogs, ['el_device_library', 'el_device_library'])
                self.assertNotIn('dl_repair', callbacks)


if __name__ == '__main__':
    unittest.main()
