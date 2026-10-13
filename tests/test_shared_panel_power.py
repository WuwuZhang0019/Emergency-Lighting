"""Date: 2026-10-13. Panel edits persist as catalog defaults across panels."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Pair, Symbol, truth
from test_diagram_store import dump
from test_device_recognition import DeviceRecognitionTests


class SharedPanelPowerTests(unittest.TestCase):
    setUp = DeviceRecognitionTests.setUp
    call = DeviceRecognitionTests.call
    get = DeviceRecognitionTests.get
    put = DeviceRecognitionTests.put
    entry = DeviceRecognitionTests.entry
    add = DeviceRecognitionTests.add
    fs = DeviceRecognitionTests.fs
    model = DeviceRecognitionTests.model

    def panel(self, folder, draft=False):
        result, powers, _ = self.model(('Lamp',))
        if draft:
            entry = self.get('devices', self.cat)[0]
            for key, value in [('watts', None), ('status', Symbol('DRAFT')),
                               ('active', None), ('ground-confirmed', None)]:
                entry = self.put(key, value, entry)
            self.cat = self.call('EL:DLUpsert', self.cat, entry)
        root = self.fs(folder)
        Path(folder, 'catalog.eld').write_text(dump(self.cat), encoding='utf-8')
        snapshot = self.call('EL:DLSnapshotLoad', root)
        prepared = self.call('EL:DLPrepare', result, powers, snapshot, None)
        self.h.set('*EL:DLSESSIONSNAPSHOT*', snapshot)
        self.h.set('*EL:PANELDRAFT*', self.get('result', prepared))
        self.h.set('*EL:PANELPOWERS*', self.get('powers', prepared))
        self.h.set('*EL:THUMBPAGE*', 0)
        self.tiles = {'b_watts0': '' if draft else '5'}
        self.messages = []
        self.h.builtins.update({
            'GET_TILE': lambda key: self.tiles.get(key, ''),
            'MODE_TILE': lambda *_: None,
            'EL:PANELFILL': lambda: None,
            'EL:PANELTEXT': lambda key, text: self.messages.append(text),
            'EL:REMEMBERPANELPOWERS': lambda *_: True,
            'EL:THUMBREFRESH': lambda *_: None,
        })
        return result, snapshot

    def test_actual_power_callback_persists_draft_catalog_and_next_panel_alias_uses_it(self):
        with tempfile.TemporaryDirectory() as folder:
            result, before = self.panel(folder, draft=True)
            self.tiles['b_watts0'] = '7'
            self.call('EL:PanelBlockPowerChanged', 0)
            saved = self.call('EL:DLSnapshotLoad', self.fs(folder))
            entry = self.call('EL:DLFindEntry', 'Lamp', saved)
            self.assertEqual(self.get('watts', entry), 7)
            self.assertEqual(self.get('legend-file', entry),
                             self.get('legend-file', self.get('devices', self.get('catalog', before))[0]))
            self.assertEqual(self.get('status', entry), Symbol('DRAFT'))
            blocks = self.get('blocks', self.get('snapshot', result))
            source = self.put('blocks', [self.put('name', 'Old Lamp', blocks[0])], self.get('snapshot', result))
            other = self.put('panel', 'P2', self.put('snapshot', source, result))
            other = self.put('device-library', None, other)
            prepared = self.call('EL:DLPrepare', other, None, saved, None)
            self.assertEqual(self.call('EL:Get', 'OLD LAMP', self.get('powers', prepared)), 7)
            self.assertIn('保存到设备库', self.messages[-1])
            self.assertTrue(truth(self.call('EL:DLSubmissionCurrent', self.h.lookup('*EL:PANELDRAFT*'))))

    def test_plain_save_captures_unblurred_edit_and_unchanged_navigation_does_not_write(self):
        with tempfile.TemporaryDirectory() as folder:
            self.panel(folder)
            self.tiles['b_watts0'] = '0'
            self.assertTrue(truth(self.call('EL:PanelStore')))
            content = Path(folder, 'catalog.eld').read_bytes()
            entry = self.call('EL:DLFindEntry', 'Lamp', self.h.lookup('*EL:DLSESSIONSNAPSHOT*'))
            self.assertEqual(self.get('watts', entry), 0)
            self.assertTrue(truth(self.get('zero-confirmed', entry)))
            self.h.builtins['EL:DLCOMMIT'] = lambda *_: self.fail('unchanged view must not write')
            self.assertTrue(truth(self.call('EL:PanelStore')))
            self.tiles['b_watts0'] = ''
            self.assertTrue(truth(self.call('EL:PanelStore')))
            self.assertEqual(Path(folder, 'catalog.eld').read_bytes(), content)

    def test_publish_failure_preserves_input_and_pending_edit_for_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            self.panel(folder)
            before = Path(folder, 'catalog.eld').read_bytes()
            self.tiles['b_watts0'] = '9'
            self.h.builtins['EL:DLCOMMIT'] = lambda *_: None
            self.assertFalse(truth(self.call('EL:PanelStore')))
            self.assertEqual(self.call('EL:Get', 'LAMP', self.h.lookup('*EL:PANELPOWERS*')), 9)
            self.assertTrue(truth(self.get('library-power-edits', self.h.lookup('*EL:PANELDRAFT*'))))
            self.assertEqual(Path(folder, 'catalog.eld').read_bytes(), before)
            del self.h.builtins['EL:DLCOMMIT']
            self.assertTrue(truth(self.call('EL:PanelStore')))
            saved = self.call('EL:DLSnapshotLoad', self.fs(folder))
            self.assertEqual(self.get('watts', self.call('EL:DLFindEntry', 'Lamp', saved)), 9)

    def test_batch_uses_single_catalog_revision_and_rejects_conflicting_aliases(self):
        with tempfile.TemporaryDirectory() as folder:
            _, snapshot = self.panel(folder)
            edits = self.h.run("'((\"LAMP\" . 8) (\"OTHER\" . 3))")
            saved = self.call('EL:DLPublishPowerEdits', snapshot, edits)
            self.assertEqual(self.get('revision', self.get('catalog', saved)),
                             self.get('revision', self.get('catalog', snapshot)) + 1)
            original = Path(folder, 'catalog.eld').read_bytes()
            with self.assertRaises(RuntimeError):
                self.call('EL:DLPublishPowerEdits', saved,
                          self.h.run("'((\"LAMP\" . 8) (\"OLD LAMP\" . 2))"))
            self.assertEqual(Path(folder, 'catalog.eld').read_bytes(), original)

    def test_editor_default_refresh_keeps_other_unsaved_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            _, before = self.panel(folder)
            entry = self.get('devices', self.get('catalog', before))[0]
            edited = self.put('display', '未保存名称', self.put('watts-text', '5', entry))
            identity = self.get('device-id', entry)
            state = self.put('snapshot', before, self.put('drafts',
                self.call('EL:Put', identity, edited, None), None))
            self.h.set('*EL:DLUISTATE*', state)
            self.h.builtins['EL:DLUIFIELDS'] = lambda: None
            edits = self.h.run("'((\"LAMP\" . 6))")
            saved = self.call('EL:DLPublishPowerEdits', before, edits)
            self.call('EL:DLPanelPowerSnapshot', saved, edits)
            draft = self.call('EL:Get', identity, self.get('drafts', self.h.lookup('*EL:DLUISTATE*')))
            self.assertEqual(self.get('display', draft), '未保存名称')
            self.assertEqual(self.get('watts-text', draft), '6')
            self.assertEqual(self.get('revision', draft), self.get('revision', entry) + 1)

    def test_new_metadata_entry_adopts_editor_draft_without_losing_unsaved_name(self):
        with tempfile.TemporaryDirectory() as folder:
            _, before = self.panel(folder)
            draft = self.call('EL:DLEntryNew', self.get('catalog', before), 'Unknown')
            identity = self.get('device-id', draft)
            draft = self.put('display', '未保存设备名称', self.put('watts-text', '', draft))
            state = self.put('snapshot', before, self.put('drafts',
                self.call('EL:Put', identity, draft, None), None))
            self.h.set('*EL:DLUISTATE*', state)
            self.h.builtins['EL:DLUIFIELDS'] = lambda: None
            edits = self.h.run("'((\"UNKNOWN\" . 4))")
            saved = self.call('EL:DLPublishPowerEdits', before, edits)
            self.call('EL:DLPanelPowerSnapshot', saved, edits)
            draft = self.call('EL:Get', identity, self.get('drafts', self.h.lookup('*EL:DLUISTATE*')))
            self.assertEqual(self.get('display', draft), '未保存设备名称')
            self.assertEqual(self.get('watts-text', draft), '4')
            self.assertEqual(self.get('revision', draft), 1)

    def test_external_change_and_invalid_input_do_not_overwrite_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            self.panel(folder)
            path = Path(folder, 'catalog.eld')
            original = path.read_bytes()
            self.tiles['b_watts0'] = '1.5'
            self.assertFalse(truth(self.call('EL:PanelStore')))
            self.assertEqual(path.read_bytes(), original)
            path.write_bytes(original + b'\n')
            self.tiles['b_watts0'] = '8'
            self.assertFalse(truth(self.call('EL:PanelStore')))
            self.assertEqual(path.read_bytes(), original + b'\n')
            self.assertEqual(self.call('EL:Get', 'LAMP', self.h.lookup('*EL:PANELPOWERS*')), 8)

    def test_power_only_publication_keeps_preview_without_loading_legends(self):
        with tempfile.TemporaryDirectory() as folder:
            self.panel(folder)
            legend = ['existing.sld', [800, 600]]
            self.h.set('*EL:THUMBCACHE*', [Pair('Lamp', legend)])
            self.h.builtins['EL:THUMBREFRESH'] = lambda *_: self.fail('power-only legend reload')
            self.tiles['b_watts0'] = '8'
            self.call('EL:PanelBlockPowerChanged', 0)
            self.assertEqual(self.call('EL:Get', 'Lamp', self.h.lookup('*EL:THUMBCACHE*')), legend)
            saved = self.call('EL:DLSnapshotLoad', self.fs(folder))
            self.assertEqual(self.get('watts', self.call('EL:DLFindEntry', 'Lamp', saved)), 8)

    def test_power_publication_refreshes_legend_after_alias_becomes_catalog_name(self):
        with tempfile.TemporaryDirectory() as folder:
            self.panel(folder, draft=True)
            result = self.h.lookup('*EL:PANELDRAFT*')
            source = self.get('snapshot', result)
            blocks = [self.put('name', 'Old Lamp', self.get('blocks', source)[0])]
            result = self.put('snapshot', self.put('blocks', blocks, source), result)
            prepared = self.call('EL:DLPrepare', result, None, self.h.lookup('*EL:DLSESSIONSNAPSHOT*'), None)
            self.h.set('*EL:PANELDRAFT*', self.get('result', prepared))
            self.h.set('*EL:PANELPOWERS*', self.get('powers', prepared))
            legend = ['registered.sld', [800, 600]]
            self.h.set('*EL:THUMBCACHE*', [Pair('Old Lamp', legend)])
            del self.h.builtins['EL:THUMBREFRESH']
            self.h.builtins.update({'EL:DLLEGEND': lambda *_: legend,
                                   'EL:THUMBRESTORE': lambda: True,
                                   'EL:THUMBCAPTURE': lambda *_: self.fail('must not recapture source')})
            self.tiles['b_watts0'] = '7'
            self.call('EL:PanelBlockPowerChanged', 0)
            row = self.call('EL:PanelBlockRows')[0]
            self.assertEqual(self.get('name', row), 'Lamp')
            self.assertEqual(self.call('EL:Get', self.get('name', row), self.h.lookup('*EL:THUMBCACHE*')), legend)


if __name__ == '__main__':
    unittest.main()
