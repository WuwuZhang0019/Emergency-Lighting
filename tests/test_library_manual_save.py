"""Explicit device saves through real catalogs. Date: 2026-10-16. Native CAD pending."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Symbol, truth
import test_library_autosave as autosave
import test_library_location as location


class LibraryManualSaveTests(unittest.TestCase):
    setUp = autosave.LibraryAutosaveTests.setUp
    call = autosave.LibraryAutosaveTests.call
    get = autosave.LibraryAutosaveTests.get
    put = autosave.LibraryAutosaveTests.put
    entry = autosave.LibraryAutosaveTests.entry
    fs = autosave.LibraryAutosaveTests.fs
    editor = autosave.LibraryAutosaveTests.editor
    rows = autosave.LibraryAutosaveTests.rows

    def save(self):
        return self.h.run(self.callbacks['dl_save'])

    def test_click_collects_current_fields_without_a_focus_loss_callback(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            other = self.rows()[1]
            self.tiles.update(dl_watts='5', dl_display='备用照明')
            self.assertTrue(truth(self.save()))
            self.assertEqual(self.get('watts', self.rows()[0]), 5)
            self.assertEqual(self.get('display', self.rows()[0]), '备用照明')
            self.assertEqual(self.rows()[1], other)
            self.assertIn('已保存并核对：备用照明，5 W', self.tiles['dl_status'])
            self.assertIsNone(self.call('EL:DLUIDraft'))
            self.assertIsNone(self.h.lookup('*EL:DLUIMANUALSAVE*'))
            self.assertEqual(self.closed, [])

    def test_already_autosaved_value_is_checked_without_rewriting(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            autosave.LibraryAutosaveTests.edit(self, 'dl_watts', '17')
            original = self.path.read_bytes()
            self.h.builtins['EL:DLCOMMIT'] = lambda *args: self.fail('unchanged save wrote again')
            reads = []
            def read(path):
                reads.append(Path(path))
                return Path(path).read_text(encoding='utf-8')
            self.h.builtins['EL:DLREADTEXT'] = read
            self.assertTrue(truth(self.save()))
            self.assertEqual(reads, [self.path])
            self.assertEqual(self.path.read_bytes(), original)
            self.assertIn('17 W', self.tiles['dl_status'])

    def test_failed_unchanged_verification_keeps_input_and_blocks_close_until_verified(self):
        for failure in ('changed', 'unreadable', 'read_exception'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                self.editor(folder)
                original = self.path.read_bytes()
                reader = self.h.builtins['EL:DLREADTEXT']
                if failure == 'changed':
                    self.path.write_bytes(original + b'\n')
                elif failure == 'unreadable':
                    self.h.builtins['EL:DLREADTEXT'] = lambda *args: None
                else:
                    def fail(*args):
                        raise OSError('cannot read catalog')
                    self.h.builtins['EL:DLREADTEXT'] = fail
                changed = self.path.read_bytes()
                self.assertFalse(truth(self.save()))
                self.assertNotIn('已保存并核对', self.tiles['dl_status'])
                self.assertEqual(self.get('watts-text', self.call('EL:DLUIDraft')), '5')
                self.call('EL:DLUILeave', 0)
                self.assertEqual(self.closed, [])
                self.assertEqual(self.path.read_bytes(), changed)
                self.path.write_bytes(original)
                self.h.builtins['EL:DLREADTEXT'] = reader
                self.assertTrue(truth(self.save()))
                self.assertFalse(truth(self.get('verify-pending', self.h.lookup('*EL:DLUISTATE*'))))
                self.call('EL:DLUILeave', 0)
                self.assertEqual(self.closed, [0])

    def test_failure_never_reports_verified_success_or_discards_input(self):
        for failure in ('invalid', 'lock', 'conflict', 'write', 'exception'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                self.editor(folder)
                self.tiles['dl_watts'] = '1.5' if failure == 'invalid' else '19'
                if failure == 'lock':
                    Path(folder, '.write-lock').write_text('other-writer', encoding='ascii')
                elif failure == 'conflict':
                    self.path.write_bytes(self.path.read_bytes() + b'\n')
                elif failure == 'write':
                    self.h.builtins['EL:DLCOMMIT'] = lambda *args: None
                elif failure == 'exception':
                    def fail(*args):
                        raise OSError('disk write failed')
                    self.h.builtins['EL:DLCOMMIT'] = fail
                original = self.path.read_bytes()
                self.assertFalse(truth(self.save()))
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(self.get('watts-text', self.call('EL:DLUIDraft')), self.tiles['dl_watts'])
                self.assertNotIn('已保存并核对', self.tiles['dl_status'])
                self.assertEqual(self.closed, [])
                self.assertIsNone(self.h.lookup('*EL:DLUIMANUALSAVE*'))

    def test_no_entry_or_deleted_entry_cannot_report_a_successful_save(self):
        for deleted in (False, True):
            with self.subTest(deleted=deleted), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                self.editor(folder)
                if deleted:
                    self.call('EL:DLUISetDraft', self.put('status', Symbol('DELETED'), self.call('EL:DLUIEntry')))
                else:
                    self.h.set('*EL:DLUISTATE*', self.put('selected', None, self.h.lookup('*EL:DLUISTATE*')))
                original = self.path.read_bytes()
                modes = {}
                self.h.builtins['MODE_TILE'] = lambda key, value: modes.__setitem__(key, value)
                self.call('EL:DLUIFields')
                self.assertEqual(modes['dl_save'], 1)
                self.assertFalse(truth(self.save()))
                self.assertEqual(self.path.read_bytes(), original)
                self.assertIn('请选择未删除的设备', self.tiles['dl_status'])

    def test_pending_legend_still_allows_explicit_parameter_save(self):
        with tempfile.TemporaryDirectory() as folder:
            self.editor(folder)
            modes = {}
            job = self.h.run("'((token . \"pending-legend\"))")
            self.h.set('*EL:DLCAPTUREJOB*', job)
            self.h.builtins['MODE_TILE'] = lambda key, value: modes.__setitem__(key, value)
            self.call('EL:DLUIFields')
            self.assertEqual(modes['dl_save'], 0)
            self.assertEqual(modes['dl_pick'], 1)
            self.tiles['dl_watts'] = '1'
            self.assertTrue(truth(self.save()))
            self.assertEqual(self.get('watts', self.rows()[0]), 1)
            self.assertEqual(self.h.lookup('*EL:DLCAPTUREJOB*'), job)


class LibraryManualSaveDialogTests(unittest.TestCase):
    fixture = location.LibraryLocationDialogTests.fixture

    def test_main_panel_save_button_writes_and_keeps_the_same_dialog_and_capacity(self):
        f, callbacks, _ = self.fixture()
        def save():
            f.call('EL:PanelCapacity', 'p_600')
            f.tiles.update(dl_watts='5', dl_display='备用照明')
            f.invoke_action(callbacks, 'dl_save')
            self.assertIn('已保存并核对：备用照明，5 W', f.tiles['dl_status'])
            self.assertEqual(f.tiles['p_capacity'], 'p_600')
            self.assertIsNone(f.closed)
            f.invoke_action(callbacks, 'cancel')
        f.actions = [save]
        f.dialog()
        self.assertEqual(f.dialogs, ['el_panel'])
        row = f.get('devices', f.call('EL:DLParse', self.catalog_path.read_text(encoding='utf-8')))[0]
        self.assertEqual(f.get('watts', row), 5)

    def test_standalone_save_button_writes_and_keeps_the_same_editor(self):
        f, callbacks, _ = self.fixture()
        f.call('EL:DLUIPanelBegin', f.call('EL:DLSnapshot'))
        f.h.set('*EL:DLUIHOST*', Symbol('STANDALONE'))
        def save():
            f.tiles.update(dl_watts='1', dl_display='疏散指示灯')
            f.invoke_action(callbacks, 'dl_save')
            self.assertIn('已保存并核对：疏散指示灯，1 W', f.tiles['dl_status'])
            self.assertIsNone(f.closed)
            f.invoke_action(callbacks, 'dl_close')
        f.actions = [save]
        f.call('EL:DLUIRun')
        self.assertEqual(f.dialogs, ['el_device_library'])
        row = f.get('devices', f.call('EL:DLParse', self.catalog_path.read_text(encoding='utf-8')))[0]
        self.assertEqual(f.get('watts', row), 1)


if __name__ == '__main__':
    unittest.main()
