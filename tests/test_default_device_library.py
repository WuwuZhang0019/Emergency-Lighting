"""Bundled defaults, upgrades and interrupted installs. Date: 2026-10-12. CAD pending."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Pair, Symbol, truth
import test_device_assets as assets
from test_diagram_store import dump

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/default-device-library'


class DefaultDeviceLibraryTests(unittest.TestCase):
    setUp = assets.DeviceAssetsTests.setUp
    call = assets.DeviceAssetsTests.call
    get = assets.DeviceAssetsTests.get
    put = assets.DeviceAssetsTests.put
    entry = assets.DeviceAssetsTests.entry
    fs = assets.DeviceAssetsTests.fs
    binary = assets.DeviceAssetsTests.binary

    def prepare(self, folder):
        root = self.fs(folder)
        self.binary()
        self.h.set('*EL:ROOT*', ROOT.as_posix() + '/')
        self.h.set('*EL:DLROOT*', root)
        self.defaults = self.call('EL:DLParse', (SOURCE / 'catalog.eld').read_text(encoding='utf-8-sig'))
        self.assertTrue(truth(self.defaults))
        return root

    def assert_assets(self, snapshot):
        root = Path(self.get('root', snapshot))
        for seed in self.get('devices', self.defaults):
            row = self.call('EL:DLDefaultMatch', seed, self.get('catalog', snapshot))
            self.assertIsNotNone(row)
            if self.get('status', row) == Symbol('DELETED'):
                continue
            for key in ('block-file', 'legend-file'):
                self.assertEqual((root / self.get(key, row)).read_bytes(),
                                 (SOURCE / self.get(key, seed)).read_bytes())

    def test_first_open_in_a_different_windows_user_library_installs_all_49(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            self.h.builtins['GETFILED'] = lambda *a: self.fail('first open asked for a library')
            self.h.builtins['EL:DLPICKDEVICES'] = lambda: self.fail('defaults asked for CAD picking')
            self.h.builtins['EL:DLUIRUN'] = lambda: True
            self.assertTrue(truth(self.call('EL:DLUIOpen')))
            state = self.h.lookup('*EL:DLUISTATE*')
            snapshot = self.get('snapshot', state)
            rows = self.get('devices', self.get('catalog', snapshot))
            self.assertEqual(len(rows), 49)
            self.assertEqual(self.get('root', snapshot), root)
            self.assertEqual(self.get('revision', self.get('catalog', snapshot)), 1)
            self.assertEqual(self.get('selected', state), self.get('device-id', rows[0]))
            self.assertEqual(sum(bool(self.get('is-ground', row)) for row in rows), 2)
            for row in rows:
                self.assertIsNone(self.get('watts', row))
                self.assertIsNone(self.get('zero-confirmed', row))
                self.assertFalse(truth(self.get('active', row)))
                self.assertEqual(self.get('status', row), Symbol('DRAFT'))
            self.assert_assets(snapshot)
            self.assertFalse(Path(d, '.write-lock').exists())

    def test_repeated_startup_and_statistics_read_do_not_write_or_export_again(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            snapshot = self.call('EL:DLDefaultStartup')
            before = {p.relative_to(d).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in Path(d).rglob('*') if p.is_file()}
            self.h.builtins['VL-FILE-COPY'] = lambda *a: self.fail('repeat startup recopied an asset')
            self.h.builtins['EL:DLWRITETEXT'] = lambda *a: self.fail('repeat startup rewrote the index')
            self.h.builtins['EL:DLCAPTURESTART'] = lambda *a: self.fail('repeat startup exported graphics')
            self.assertEqual(self.call('EL:DLDefaultStartup'), snapshot)
            self.assertEqual(self.call('EL:DLSnapshot'), self.put('scope', None, snapshot))
            self.assertEqual(before, {p.relative_to(d).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                            for p in Path(d).rglob('*') if p.is_file()})
            self.assertEqual(self.h.lookup('*EL:DLROOT*'), root)

    def test_sparse_existing_library_keeps_user_values_names_identity_and_graphics(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            snapshot = self.call('EL:DLSnapshotLoad', root)
            seed = self.get('devices', self.defaults)[-1]
            row = self.entry('我的事故灯', watts=9, ground=None)
            row = self.put('aliases', [self.get('block-name', seed), '本人旧块名'], row)
            row = self.put('display', '用户已编辑名称', row)
            row = self.call('EL:DLAssetInstall', snapshot, row,
                            str(SOURCE / self.get('block-file', seed)), str(SOURCE / self.get('legend-file', seed)))
            catalog = self.call('EL:DLUpsert', self.get('catalog', snapshot), row)
            self.assertTrue(truth(self.call('EL:DLCommit', snapshot, catalog)))
            original = self.get('devices', catalog)[0]
            graphic = Path(d, self.get('block-file', original))
            graphic.write_bytes(b'AC1015user-custom-geometry')
            upgraded = self.call('EL:DLDefaultSnapshot', root)
            self.assertEqual(self.get('library-id', self.get('catalog', upgraded)), self.get('library-id', catalog))
            self.assertEqual(len(self.get('devices', self.get('catalog', upgraded))), 49)
            self.assertEqual(self.get('devices', self.get('catalog', upgraded))[0], original)
            self.assertEqual(graphic.read_bytes(), b'AC1015user-custom-geometry')
            self.assertEqual(self.get('revision', self.get('catalog', upgraded)), 2)
            self.assertEqual(Path(d, 'history/1.eld').read_text(encoding='utf-8'), dump(catalog))

    def test_saved_graphicless_draft_reuses_identity_and_preserves_power_fields(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            snapshot = self.call('EL:DLSnapshotLoad', root)
            row = self.entry('$equip$00001198', watts=7, ground=True, ready=False)
            catalog = self.call('EL:DLUpsert', self.get('catalog', snapshot), row)
            self.assertTrue(truth(self.call('EL:DLCommit', snapshot, catalog)))
            upgraded = self.call('EL:DLDefaultSnapshot', root)
            row = self.call('EL:DLFindEntry', '$equip$00001198', upgraded)
            self.assertEqual(self.get('device-id', row), 'ELDEV1')
            self.assertEqual(self.get('watts', row), 7)
            self.assertTrue(truth(self.get('is-ground', row)))
            self.assertEqual(self.get('status', row), Symbol('DRAFT'))
            self.assert_assets(upgraded)

    def test_user_deleted_default_is_not_restored_even_if_its_assets_are_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            snapshot = self.call('EL:DLSnapshotLoad', root)
            row = self.put('status', Symbol('DELETED'), self.entry('$equip$00001198', watts=None, ready=False))
            catalog = self.call('EL:DLUpsert', self.get('catalog', snapshot), row)
            self.assertTrue(truth(self.call('EL:DLCommit', snapshot, catalog)))
            upgraded = self.call('EL:DLDefaultSnapshot', root)
            rows = self.get('devices', self.get('catalog', upgraded))
            self.assertEqual(len(rows), 49)
            self.assertEqual(rows[0], self.get('devices', catalog)[0])
            self.assertFalse(Path(d, 'assets/ELDEV1').exists())

    def test_existing_unsaved_power_form_receives_default_assets_and_can_be_saved(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            snapshot = self.call('EL:DLSnapshotLoad', root)
            row = self.entry('$equip$00001198', watts=7, ready=False)
            catalog = self.call('EL:DLUpsert', self.get('catalog', snapshot), row)
            self.assertTrue(truth(self.call('EL:DLCommit', snapshot, catalog)))
            previous = self.call('EL:DLSnapshotLoad', root)
            self.h.set('*EL:DLUISTATE*', [Pair(Symbol('SNAPSHOT'), previous), Pair(Symbol('QUERY'), ''), [Symbol('DRAFTS')]])
            draft = self.put('watts-text', '11', self.get('devices', catalog)[0])
            self.call('EL:DLUISetDraft', draft)
            snapshot = self.call('EL:DLDefaultSnapshot', root)
            self.call('EL:DLUIAdoptSnapshot', snapshot)
            draft = self.call('EL:DLUIDraft')
            self.assertEqual(self.get('watts-text', draft), '11')
            self.assertTrue(truth(self.call('EL:DLEntryAssets', draft)))
            edited = self.call('EL:DLUIToEntry', draft)
            self.assertEqual(self.get('watts', edited), 11)
            self.assertTrue(truth(self.call('EL:DLUpsert', self.get('catalog', snapshot), edited)))

    def test_interrupted_copy_keeps_old_index_releases_lock_and_can_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            snapshot = self.call('EL:DLSnapshotLoad', root)
            catalog = self.call('EL:DLUpsert', self.get('catalog', snapshot), self.entry('用户其他设备', ready=False))
            self.assertTrue(truth(self.call('EL:DLCommit', snapshot, catalog)))
            original = Path(d, 'catalog.eld').read_bytes()
            copy = self.h.builtins['VL-FILE-COPY']
            count = [0]
            def interrupted(a, b):
                count[0] += 1
                return None if count[0] == 19 else copy(a, b)
            self.h.builtins['VL-FILE-COPY'] = interrupted
            failed = self.call('EL:DLDefaultSnapshot', root)
            self.assertEqual(self.get('catalog', failed), catalog)
            self.assertEqual(Path(d, 'catalog.eld').read_bytes(), original)
            self.assertIn('安装未完成', self.h.lookup('*EL:DLERROR*'))
            self.assertIn('复制默认设备', self.h.lookup('*EL:DLERROR*'))
            self.assertFalse(Path(d, '.write-lock').exists())
            self.h.builtins['VL-FILE-COPY'] = copy
            retried = self.call('EL:DLDefaultSnapshot', root)
            self.assertEqual(len(self.get('devices', self.get('catalog', retried))), 50)
            self.assert_assets(retried)

    def test_locked_or_corrupt_library_is_preserved_and_default_install_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            path = Path(d, 'catalog.eld')
            path.write_text('(broken)', encoding='utf-8')
            self.assertFalse(truth(self.call('EL:DLDefaultSnapshot', root)))
            self.assertEqual(path.read_text(), '(broken)')
            self.assertIn('损坏', self.h.lookup('*EL:DLERROR*'))
            Path(d, '.write-lock').write_bytes(b'op-another-writer')
            self.assertFalse(truth(self.call('EL:DLDefaultSnapshot', root)))
            self.assertEqual(Path(d, '.write-lock').read_bytes(), b'op-another-writer')
            self.assertFalse(Path(d, 'assets').exists())

    def test_default_install_preserves_unsaved_forms_and_rebinds_colliding_new_ids(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.prepare(d)
            old = self.call('EL:DLSnapshotLoad', root)
            state = [Pair(Symbol('SNAPSHOT'), old), Pair(Symbol('QUERY'), ''), [Symbol('DRAFTS')]]
            self.h.set('*EL:DLUISTATE*', state)
            row = self.put('watts-text', '7.5 invalid raw', self.entry('$equip$00001198', watts=None, ready=False))
            self.call('EL:DLUISetDraft', row)
            other = self.put('device-id', 'ELDEV2', self.entry('未入库其他设备', ready=False))
            self.call('EL:DLUISetDraft', self.put('aliases-text', '原始;输入', other))
            snapshot = self.call('EL:DLDefaultSnapshot', root)
            self.call('EL:DLUIAdoptSnapshot', snapshot)
            state = self.h.lookup('*EL:DLUISTATE*')
            drafts = self.get('drafts', state)
            rebound = self.call('EL:Get', 'ELDEV49', drafts)
            self.assertEqual(self.get('watts-text', rebound), '7.5 invalid raw')
            self.assertTrue(truth(self.call('EL:DLEntryAssets', rebound)))
            unrelated = self.call('EL:Get', 'ELDEV50', drafts)
            self.assertEqual(self.get('aliases-text', unrelated), '原始;输入')
            self.assertEqual(self.get('block-name', unrelated), '未入库其他设备')
            self.assertEqual(len(self.call('EL:DLUIRows')), 50)

    def test_utf8_stream_skips_bom_without_losing_chinese_and_preserves_invalid_reason(self):
        text = '(设备中文 "引号" \\ 路径)'
        props = {}
        content = [b'\xef\xbb\xbf' + text.encode('utf-8')]
        calls = []
        def invoke(stream, name, *args):
            calls.append(str(name))
            if str(name) == 'OPEN':
                self.assertEqual(args, (None, 0, -1, '', ''))
            if str(name) == 'READ':
                return list(content[0])
            if str(name) == 'READTEXT':
                return content[0][props.get('POSITION', 0):].decode('utf-8')
        self.h.builtins.update({
            'VLAX-PUT-PROPERTY': lambda s,k,v: props.__setitem__(str(k),v),
            'VLAX-GET-PROPERTY': lambda s,k: len(content[0]),
            'VLAX-INVOKE-METHOD': invoke,
            'VLAX-VARIANT-VALUE': lambda v:v,
            'VLAX-SAFEARRAY->LIST': lambda v:v,
        })
        self.assertEqual(self.call('EL:DLReadStream', 'stream', '中文路径/catalog.eld'), text)
        self.assertEqual(props['POSITION'], 3)
        content[0] = b'bad\x80'
        self.assertFalse(truth(self.call('EL:DLReadStream', 'stream', 'path')))
        self.assertEqual(self.h.lookup('*EL:DLERROR*'), '设备库不是有效 UTF-8，原文件保留。')

    def test_ado_write_and_asset_reads_supply_complete_method_arguments(self):
        calls = []
        positions = {}
        data = [65, 67, 49, 48, 51, 50]

        def invoke(stream, name, *args):
            name = str(name)
            calls.append((name, args))
            if name == 'OPEN':
                self.assertEqual(args, (None, 0, -1, '', ''))
                positions[stream] = 0
            elif name == 'WRITETEXT':
                self.assertEqual(args, ('设备库中文', 0))
            elif name == 'READ':
                self.assertEqual(len(args), 1)
                positions[stream] = len(data)
                return data
            elif name == 'SAVETOFILE':
                self.assertEqual(args, ('catalog.eld', 1))
            elif name == 'LOADFROMFILE':
                self.assertEqual(len(args), 1)
            else:
                self.fail('unexpected ADO call: ' + name)

        self.h.builtins.update({
            'VLAX-INVOKE-METHOD': invoke,
            'VLAX-PUT-PROPERTY': lambda *args: None,
            'VLAX-GET-PROPERTY': lambda s, k: len(data) if str(k) == 'SIZE' else positions[s],
            'VLAX-VARIANT-VALUE': lambda v: v,
            'VLAX-SAFEARRAY->LIST': lambda v: v,
        })
        self.assertTrue(self.call('EL:DLWriteStream', 'text', 'catalog.eld', '设备库中文'))
        self.assertEqual(self.call('EL:DLBytesWork', 'bytes', 'block.dwg', 6), data)
        self.assertTrue(self.call('EL:DLFilesEqualWork', 'a.dwg', 'b.dwg', 'left', 'right'))
        self.assertEqual(sum(name == 'OPEN' for name, args in calls), 4)

    def test_switch_failure_is_reported_and_keeps_root_and_raw_inputs(self):
        state = [Pair(Symbol('SNAPSHOT'), [Pair(Symbol('ROOT'), '/old/')]), Pair(Symbol('DRAFTS'), ['raw'])]
        self.h.set('*EL:DLUISTATE*', state)
        self.h.set('*EL:DLROOT*', '/old/')
        self.h.builtins['VL-FILENAME-DIRECTORY'] = lambda p:'/new'
        self.h.builtins['EL:DLSNAPSHOTLOAD'] = lambda r: (_ for _ in ()).throw(RuntimeError('access denied'))
        self.assertFalse(truth(self.call('EL:DLUISwitchRoot', '/new/catalog.eld')))
        self.assertEqual(self.h.lookup('*EL:DLUISTATE*'), state)
        self.assertEqual(self.h.lookup('*EL:DLROOT*'), '/old/')
        self.assertIn('access denied', self.h.lookup('*EL:DLERROR*'))
        self.assertIn('未切换', self.h.lookup('*EL:DLERROR*'))


if __name__ == '__main__':
    unittest.main()
