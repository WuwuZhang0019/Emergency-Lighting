"""Library autosave through real catalog writes. Date: 2026-10-16. Native DCL pending."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Pair, Symbol, truth
import test_device_library as backend
from test_diagram_store import dump

ROOT = Path(__file__).resolve().parents[1]


class LibraryAutosaveTests(unittest.TestCase):
    setUp = backend.DeviceLibraryTests.setUp
    call = backend.DeviceLibraryTests.call
    get = backend.DeviceLibraryTests.get
    put = backend.DeviceLibraryTests.put
    entry = backend.DeviceLibraryTests.entry
    fs = backend.DeviceLibraryTests.fs

    def editor(self, folder):
        root = self.fs(folder)
        self.cat = self.call('EL:DLUpsert', self.cat, self.entry('Lamp A'))
        self.cat = self.call('EL:DLUpsert', self.cat, self.entry('Lamp B', watts=8))
        self.path = Path(folder, 'catalog.eld')
        self.path.write_text(dump(self.cat), encoding='utf-8')
        snapshot = self.call('EL:DLSnapshotLoad', root)
        self.h.set('*EL:DLUISTATE*', [Pair(Symbol('SNAPSHOT'), snapshot),
            Pair(Symbol('SELECTED'), 'ELDEV1'), Pair(Symbol('QUERY'), ''), [Symbol('DRAFTS')]])
        self.h.set('*EL:DLUIHOST*', Symbol('STANDALONE'))
        self.tiles, self.callbacks, self.closed = {}, {}, []
        self.h.builtins.update({
            'GET_TILE': lambda key:self.tiles.get(key, ''),
            'SET_TILE': lambda key,value:self.tiles.__setitem__(key,value),
            'START_LIST': lambda *args:None, 'ADD_LIST':lambda *args:None,
            'END_LIST': lambda:None, 'MODE_TILE':lambda *args:None,
            'EL:THUMBDRAW':lambda *args:None, 'EL:DLLegend'.upper():lambda *args:None,
            'EL:DLUIASSETREADY':lambda *args:True,
            'EL:MONITORACTIONTILE':lambda key,action:self.callbacks.__setitem__(key,action),
            'DONE_DIALOG':lambda status:self.closed.append(status),
        })
        self.call('EL:DLUIFill')
        self.call('EL:DLUIAutoBind')

    def rows(self):
        snapshot = self.call('EL:DLSnapshotLoad', str(self.path.parent).replace('\\','/')+'/')
        return self.get('devices', self.get('catalog', snapshot))

    def edit(self, key, value):
        self.tiles[key] = value
        return self.h.run(self.callbacks[key])

    def test_power_callback_writes_catalog_without_pressing_the_save_button(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            other = self.rows()[1]
            self.assertTrue(truth(self.edit('dl_watts', '17')))
            self.assertEqual(self.get('watts', self.rows()[0]), 17)
            self.assertEqual(self.rows()[1], other)
            self.assertIn('已自动保存', self.tiles['dl_status'])
            self.assertIsNone(self.call('EL:DLUIDraft'))
            self.assertIn('dl_save', self.callbacks)

    def test_names_aliases_ground_zero_and_activation_all_save(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            for key,value in (('dl_display','用户设备'), ('dl_aliases','旧别名;Other'),
                              ('dl_block','New Lamp'), ('dl_ground','2'), ('dl_zero','1'),
                              ('dl_watts','0'), ('dl_active','0')):
                self.assertTrue(truth(self.edit(key,value)), key)
            row = self.rows()[0]
            for key,value in (('display','用户设备'), ('block-name','New Lamp'),
                              ('aliases',['旧别名','Other','Lamp A']), ('watts',0),
                              ('is-ground',True), ('zero-confirmed',True)):
                self.assertEqual(self.get(key,row), value)
            self.assertFalse(truth(self.get('active',row)))

    def test_switching_saves_previous_device_and_selects_original_target(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            self.tiles['dl_watts']='12'
            self.call('EL:DLUISelect','1')
            self.assertEqual(self.get('watts',self.rows()[0]),12)
            self.assertEqual(self.get('selected',self.h.lookup('*EL:DLUISTATE*')),'ELDEV2')
            self.assertEqual(self.tiles['dl_watts'],'8')

    def test_unchanged_focus_switch_and_close_do_not_rewrite_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            original=self.path.read_bytes()
            self.h.builtins['EL:DLCOMMIT']=lambda *args:self.fail('unchanged data was written')
            self.edit('dl_watts','5')
            self.call('EL:DLUISelect','1')
            self.call('EL:DLUILeave',0)
            self.assertEqual(self.closed,[0])
            self.assertEqual(self.path.read_bytes(),original)

    def test_invalid_power_keeps_file_and_raw_input_then_can_be_corrected(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            original=self.path.read_bytes()
            self.assertFalse(truth(self.edit('dl_watts','1.5')))
            self.assertEqual(self.path.read_bytes(),original)
            self.assertEqual(self.get('watts-text',self.call('EL:DLUIDraft')),'1.5')
            self.call('EL:DLUILeave',0)
            self.assertEqual(self.closed,[])
            self.assertIn('非负整数',self.tiles['dl_status'])
            self.tiles['dl_watts']='15'
            self.call('EL:DLUILeave',0)
            self.assertEqual(self.closed,[0])
            self.assertEqual(self.get('watts',self.rows()[0]),15)

    def test_close_retries_an_earlier_invalid_device_and_keeps_valid_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            self.edit('dl_watts','错误功率')
            self.call('EL:DLUISelect','1')
            self.edit('dl_watts','9')
            self.call('EL:DLUILeave',0)
            self.assertEqual(self.closed,[])
            self.assertEqual(self.tiles['dl_watts'],'错误功率')
            self.assertEqual(self.get('watts',self.rows()[1]),9)
            self.assertEqual(self.get('watts',self.rows()[0]),5)

    def test_conflict_and_lock_never_overwrite_disk_or_discard_input(self):
        for locked in (False,True):
            with self.subTest(locked=locked), tempfile.TemporaryDirectory() as folder:
                self.setUp(); self.editor(folder)
                if locked:
                    Path(folder,'.write-lock').write_text('another-writer',encoding='ascii')
                else:
                    self.path.write_text(dump(self.cat)+'\n',encoding='utf-8')
                original=self.path.read_bytes()
                self.assertFalse(truth(self.edit('dl_watts','21')))
                self.assertEqual(self.path.read_bytes(),original)
                self.assertEqual(self.get('watts-text',self.call('EL:DLUIDraft')),'21')
                self.assertIn('自动保存未完成',self.tiles['dl_status'])

    def test_write_failure_retains_draft_for_automatic_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            original=self.path.read_bytes()
            self.h.builtins['EL:DLCOMMIT']=lambda *args:None
            self.assertFalse(truth(self.edit('dl_watts','18')))
            self.assertEqual(self.path.read_bytes(),original)
            self.assertEqual(self.get('watts-text',self.call('EL:DLUIDraft')),'18')
            del self.h.builtins['EL:DLCOMMIT']
            self.call('EL:DLUILeave',0)
            self.assertEqual(self.get('watts',self.rows()[0]),18)
            self.assertEqual(self.closed,[0])

    def test_blank_power_is_saved_as_a_draft_without_implying_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            self.edit('dl_watts','')
            row=self.rows()[0]
            self.assertIsNone(self.get('watts',row))
            self.assertEqual(self.get('status',row),Symbol('DRAFT'))
            self.assertFalse(truth(self.get('active',row)))

    def test_commit_exception_is_failure_and_does_not_close_editor(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            original=self.path.read_bytes()
            def fail(*args):
                raise RuntimeError('disk write error')
            self.h.builtins['EL:DLCOMMIT']=fail
            self.assertFalse(truth(self.edit('dl_watts','19')))
            self.call('EL:DLUILeave',0)
            self.assertEqual(self.closed,[])
            self.assertEqual(self.path.read_bytes(),original)
            self.assertEqual(self.get('watts-text',self.call('EL:DLUIDraft')),'19')
            self.assertIn('disk write error',self.tiles['dl_status'])


if __name__=='__main__':
    unittest.main()
