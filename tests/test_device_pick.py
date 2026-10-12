"""Date: 2026-10-12. Direct library picks with real catalog/assets I/O and finite CAD boundaries."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Pair, Symbol, truth
import test_device_assets as assets
import test_device_ui as ui
import test_auto_wire as wire


class DevicePickTests(unittest.TestCase):
    setUp = ui.DeviceUITests.setUp
    call = ui.DeviceUITests.call
    get = ui.DeviceUITests.get
    put = ui.DeviceUITests.put
    entry = ui.DeviceUITests.entry
    fs = ui.DeviceUITests.fs
    state = ui.DeviceUITests.state
    binary = assets.DeviceAssetsTests.binary
    slide = assets.DeviceAssetsTests.slide

    def library(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.root = self.fs(folder.name); self.binary(); self.state()
        self.h.set('*EL:DLUISTATE*', self.put('snapshot', self.call('EL:DLSnapshotLoad', self.root), self.h.lookup('*EL:DLUISTATE*')))
        self.h.set(':VLAX-FALSE', 0); self.h.set(':VLAX-TRUE', -1)
        self.h.builtins.update({'GETVAR': lambda key: 0, 'EL:DLUIRUN': lambda: self.opened.append('library'),
            'EL:DLCAPTURECLOSE': lambda job: True, 'EL:EFFECTIVENAME': lambda e: e})
        self.opened, self.jobs = [], []
        def capture(snapshot, entry, entity):
            token = f'op-pick-{len(self.jobs)}'
            stage = self.folder / '.staging' / token; stage.mkdir(parents=True)
            paths = {key: str(stage / value).replace('\\', '/') for key, value in
                     {'dwg': 'block.dwg', 'slide': 'legend.sld', 'marker': 'complete.txt'}.items()}
            Path(paths['dwg']).write_bytes(b'AC1032' + entity.encode())
            job = self.put('entry', entry, self.put('snapshot', snapshot, self.put('token', token, None)))
            for key, value in paths.items(): job = self.put(key, value, job)
            self.jobs.append(job); self.h.set('*EL:DLCAPTUREJOB*', job)
            return True
        self.h.builtins['EL:DLCAPTURESTART'] = capture
        self.h.run('(setq *EL:DLUIPickSaved* 0 *EL:DLUIPickReused* 0 *EL:DLUIPickFailed* 0)')
        return self.root

    def complete(self, valid=True):
        job = self.h.lookup('*EL:DLCAPTUREJOB*')
        Path(self.get('slide', job)).write_bytes(self.slide() if valid else b'bad-sld')
        Path(self.get('marker', job)).write_text('DONE\n', encoding='utf-8')
        self.call('EL:DLCaptureResume', self.get('token', job))

    def test_multi_pick_filters_wrong_layer_xref_paper_output_and_deduplicates(self):
        f = wire.AutoWireTests(); f.setUp()
        f.block('BAD', 'ARCH', 'wrong', [0., 0., 0.])
        f.block('XREF', 'D', 'xref', [0., 0., 0.]); f.blocks['XREF'] = [Pair(70, 4)]
        f.block('PAPER', 'D', 'paper', [0., 0., 0.]); f.entities['paper'] += [Pair(410, 'Layout1')]
        # Replace the original Model row rather than trusting the selection filter.
        f.entities['paper'] = [p for p in f.entities['paper'] if p.car != 410] + [Pair(410, 'Layout1')]
        f.block('OUTPUT', 'D', 'output', [0., 0., 0.])
        f.selected[:] = ['panel', 'w1', 'wrong', 'xref', 'paper', 'output', 'a', 'b']
        f.h.builtins.update({'EL:PRESETLOAD': lambda: f.cfg, 'EL:MANAGEDENTITY': lambda e: e == 'output'})
        self.assertEqual(f.call('EL:DLPickDevices'), ['a'])

    def test_two_types_directly_publish_graphics_without_new_or_save_buttons(self):
        self.library()
        self.h.set('*EL:DLUIPICKQUEUE*', ['Lamp', 'Sign'])
        self.assertEqual(self.call('EL:DLUIPickNext'), Symbol('SUSPENDED'))
        self.complete(); self.assertEqual(self.opened, [])
        self.complete(); self.assertEqual(self.opened, ['library'])
        snap = self.call('EL:DLSnapshotLoad', self.root)
        entries = self.get('devices', self.get('catalog', snap))
        self.assertEqual([self.get('block-name', e) for e in entries], ['Lamp', 'Sign'])
        self.assertEqual([self.get('device-id', e) for e in entries], ['ELDEV1', 'ELDEV2'])
        for entry in entries:
            self.assertIsNone(self.get('watts', entry))
            self.assertEqual(self.get('status', entry), Symbol('DRAFT'))
            self.assertFalse(truth(self.get('active', entry)))
            self.assertTrue(truth(self.call('EL:DLLegend', entry, snap)))
            self.assertTrue(truth(self.call('EL:DLDWGValid', self.root + self.get('block-file', entry))))
        self.assertEqual(self.call('EL:DLRecognitionNames', snap), ['Lamp', 'Sign'])
        self.assertIsNone(self.call('EL:DLLookup', 'Lamp', snap))
        self.assertEqual(self.h.lookup('*EL:DLUIPICKSAVED*'), 2)
        self.assertFalse(list((self.folder / '.staging').rglob('block.dwg')))

    def test_existing_graphic_is_reused_and_saved_watts_are_preserved(self):
        self.library(); self.h.set('*EL:DLUIPICKQUEUE*', ['Lamp'])
        self.call('EL:DLUIPickNext'); self.complete()
        snapshot = self.call('EL:DLSnapshotLoad', self.root)
        entry = self.get('devices', self.get('catalog', snapshot))[0]
        entry = self.put('watts', 7, self.put('ground-confirmed', True,
            self.put('status', Symbol('READY'), self.put('active', True, entry))))
        self.assertTrue(self.call('EL:DLCommit', snapshot, self.call('EL:DLUpsert', self.get('catalog', snapshot), entry)))
        snapshot = self.call('EL:DLSnapshotLoad', self.root)
        self.h.set('*EL:DLUISTATE*', self.put('snapshot', snapshot, self.h.lookup('*EL:DLUISTATE*')))
        before = (self.folder / 'catalog.eld').read_bytes()
        self.h.set('*EL:DLUIPICKQUEUE*', ['Lamp']); self.call('EL:DLUIPickNext')
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual((self.folder / 'catalog.eld').read_bytes(), before)
        self.assertEqual(self.h.lookup('*EL:DLUIPICKREUSED*'), 1)
        self.assertEqual(self.get('watts', self.call('EL:DLUIEntry')), 7)

    def test_invalid_slide_is_not_published_and_next_type_still_succeeds(self):
        self.library(); self.h.set('*EL:DLUIPICKQUEUE*', ['Bad', 'Good'])
        self.call('EL:DLUIPickNext'); self.complete(valid=False); self.complete()
        entries = self.get('devices', self.get('catalog', self.call('EL:DLSnapshotLoad', self.root)))
        self.assertEqual([self.get('block-name', e) for e in entries], ['Good'])
        self.assertEqual(self.h.lookup('*EL:DLUIPICKFAILED*'), 1)
        self.assertIn('未完成 1 种', self.h.lookup('*EL:DLUINOTICE*'))

    def test_concurrent_catalog_edit_blocks_publication_and_keeps_capture_for_retry(self):
        self.library(); self.h.set('*EL:DLUIPICKQUEUE*', ['Lamp'])
        self.call('EL:DLUIPickNext')
        snapshot = self.get('snapshot', self.h.lookup('*EL:DLCAPTUREJOB*'))
        other = self.put('device-id', 'ELDEV8', self.entry('Other', ready=False))
        self.assertTrue(self.call('EL:DLCommit', snapshot, self.call('EL:DLUpsert', self.get('catalog', snapshot), other)))
        before = (self.folder / 'catalog.eld').read_bytes()
        self.complete()
        self.assertEqual((self.folder / 'catalog.eld').read_bytes(), before)
        self.assertIsNotNone(self.get('captured', self.call('EL:DLUIEntry')))
        self.assertEqual(self.h.lookup('*EL:DLUIPICKSAVED*'), 0)
        self.assertEqual(self.h.lookup('*EL:DLUIPICKFAILED*'), 1)

    def test_picking_retains_same_name_and_unrelated_invalid_raw_drafts(self):
        self.library()
        draft = self.put('watts-text', '1.5', self.put('display', '未保存名称', self.call('EL:DLEntryNew', self.cat, 'Lamp')))
        self.call('EL:DLUISetDraft', draft)
        other = self.put('device-id', 'ELDEV9', self.put('watts-text', 'bad', self.entry('Other', ready=False)))
        self.call('EL:DLUISetDraft', other)
        self.h.set('*EL:DLUIPICKQUEUE*', ['Lamp']); self.call('EL:DLUIPickNext'); self.complete()
        state = self.h.lookup('*EL:DLUISTATE*')
        kept = self.call('EL:Get', 'ELDEV1', self.get('drafts', state))
        self.assertEqual(self.get('watts-text', kept), '1.5')
        self.assertEqual(self.get('display', kept), '未保存名称')
        self.assertEqual(self.get('revision', kept), 1)
        self.assertEqual(self.call('EL:Get', 'ELDEV9', self.get('drafts', state)), other)
        saved = self.get('devices', self.get('catalog', self.get('snapshot', state)))[0]
        self.assertIsNone(self.get('watts', saved))
        self.assertEqual(self.get('display', saved), 'Lamp')

    def test_asset_copy_failure_keeps_catalog_and_captured_graphic(self):
        self.library(); self.h.set('*EL:DLUIPICKQUEUE*', ['Lamp']); self.call('EL:DLUIPickNext')
        self.h.builtins['VL-FILE-COPY'] = lambda *args: None
        self.complete()
        self.assertFalse((self.folder / 'catalog.eld').exists())
        self.assertIsNotNone(self.get('captured', self.call('EL:DLUIEntry')))
        self.assertEqual(self.h.lookup('*EL:DLUIPICKSAVED*'), 0)

    def test_deleted_source_in_queue_does_not_prevent_other_type_from_publishing(self):
        self.library()
        def name(entity):
            if entity == 'deleted': raise RuntimeError('erased source device')
            return entity
        self.h.builtins['EL:EFFECTIVENAME'] = name
        self.h.set('*EL:DLUIPICKQUEUE*', ['deleted', 'Good'])
        self.call('EL:DLUIPickNext'); self.complete()
        entries = self.get('devices', self.get('catalog', self.call('EL:DLSnapshotLoad', self.root)))
        self.assertEqual([self.get('block-name', e) for e in entries], ['Good'])
        self.assertEqual(self.h.lookup('*EL:DLUIPICKFAILED*'), 1)

    def test_picker_is_enabled_without_selected_entry_and_escape_returns_to_same_drafts(self):
        self.library(); self.h.builtins.pop('EL:DLUIRUN')
        self.h.set('*EL:ROOT*', 'plugin/'); self.h.set('*EL:DLUIPICKREQUESTED*', True)
        tiles, modes, actions, seen = {}, {}, {}, []
        self.h.builtins.update({'LOAD_DIALOG': lambda *args: 1, 'UNLOAD_DIALOG': lambda *args: None,
            'NEW_DIALOG': lambda *args: True, 'SET_TILE': lambda k,v: tiles.__setitem__(k,v),
            'MODE_TILE': lambda k,v: modes.__setitem__(k,v), 'GET_TILE': lambda k: tiles.get(k,''),
            'START_LIST': lambda *args: None, 'END_LIST': lambda: None, 'ADD_LIST': lambda *args: None,
            'ACTION_TILE': lambda k,v: actions.__setitem__(k,v), 'EL:THUMBDRAW': lambda *args: None,
            'EL:DLPICKDEVICES': lambda: seen.append('pick') or None,
            'START_DIALOG': lambda: seen.append(('dialog', modes['dl_pick'])) or 0})
        before = self.h.lookup('*EL:DLUISTATE*')
        self.call('EL:DLUIRun')
        self.assertEqual(seen, ['pick', ('dialog', 0)])
        self.assertEqual(self.h.lookup('*EL:DLUISTATE*'), before)
        self.assertFalse((self.folder / 'catalog.eld').exists())


if __name__ == '__main__': unittest.main()
