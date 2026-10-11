"""Library draft and CRUD callbacks. Date: 2026-10-11. No native DCL acceptance."""
from pathlib import Path
import re
import tempfile
import unittest

import test_device_library as backend
from autolisp_host import Pair, Symbol, truth, parse


class DeviceUITests(unittest.TestCase):
    setUp = backend.DeviceLibraryTests.setUp
    call = backend.DeviceLibraryTests.call
    get = backend.DeviceLibraryTests.get
    put = backend.DeviceLibraryTests.put
    entry = backend.DeviceLibraryTests.entry
    fs = backend.DeviceLibraryTests.fs

    def state(self, catalog=None):
        catalog = catalog or self.cat
        state = [Pair(Symbol('SNAPSHOT'),[Pair(Symbol('CATALOG'), catalog)]), Pair(Symbol('QUERY'),''),
            [Symbol('DRAFTS')], [Symbol('SELECTED')]]
        self.h.set('*EL:DLUISTATE*',state)

    def test_invalid_watts_text_is_retained_without_replacing_catalog(self):
        self.state()
        row = self.put('watts-text','错误值',self.entry())
        self.call('EL:DLUISetDraft',row)
        self.assertFalse(truth(self.call('EL:DLUIToEntry',row)))
        self.assertEqual(self.get('watts-text',self.call('EL:DLUIEntry')),'错误值')
        self.assertEqual(self.get('revision',self.cat),0)

    def test_explicit_false_ground_zero_and_alias_input_survive_conversion(self):
        self.state()
        row = self.put('watts-text','0',self.put('aliases-text','旧灯;Lamp',self.entry(watts=0)))
        converted = self.call('EL:DLUIToEntry',row)
        self.assertFalse(truth(self.get('is-ground',converted)))
        self.assertTrue(truth(self.get('ground-confirmed',converted)))
        self.assertEqual(self.get('watts',converted),0)
        self.assertEqual(self.get('aliases',converted),['旧灯','Lamp'])
        self.assertTrue(truth(self.call('EL:DLCatalogValid', self.call('EL:DLUpsert', self.cat, converted))))

    def test_incomplete_device_remains_draft_and_disabled(self):
        self.state()
        converted = self.call('EL:DLUIToEntry',self.entry(ready=False))
        self.assertEqual(self.get('status',converted),Symbol('DRAFT'))
        self.assertFalse(truth(self.get('active',converted)))

    def test_multiple_new_drafts_keep_separate_ids_and_search_results(self):
        self.state()
        self.h.builtins.update({'EL:Dluistore'.upper():lambda: True,'EL:DLUIFILL':lambda:None,'EL:DLUISTATUS':lambda _:None})
        self.call('EL:DLUINew'); first = self.call('EL:DLUIEntry')
        self.call('EL:DLUINew'); second = self.call('EL:DLUIEntry')
        self.assertNotEqual(self.get('device-id',first),self.get('device-id',second))
        self.assertEqual(len(self.call('EL:DLUIRows')),2)
        self.call('EL:DLUISetDraft',self.put('display','专用标志灯',second))
        state=self.put('query','标志灯',self.h.lookup('*EL:DLUISTATE*')); self.h.set('*EL:DLUISTATE*',state)
        self.assertEqual(len(self.call('EL:DLUIRows')),1)
        self.assertEqual(len(self.get('drafts',self.h.lookup('*EL:DLUISTATE*'))),2)

    def test_store_preserves_empty_and_invalid_raw_fields_when_switching(self):
        self.state(); self.call('EL:DLUISetDraft',self.entry())
        tiles={'dl_block':'Lamp','dl_display':'待定设备','dl_aliases':'别名A;B','dl_watts':'1.5','dl_ground':'1','dl_zero':'0','dl_active':'1','dl_keep_old':'1'}
        self.h.builtins['GET_TILE']=tiles.__getitem__
        self.call('EL:DLUIStore')
        row=self.call('EL:DLUIEntry')
        self.assertEqual(self.get('watts-text',row),'1.5')
        self.assertFalse(truth(self.get('is-ground',row)))
        self.assertTrue(truth(self.get('ground-confirmed',row)))

    def test_full_crud_publishes_and_refresh_keeps_other_unsaved_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.fs(d); snap=self.call('EL:DLSnapshotLoad',root)
            self.state(); self.h.set('*EL:DLUISTATE*',self.put('snapshot',snap,self.h.lookup('*EL:DLUISTATE*')))
            messages=[]
            self.h.builtins.update({'EL:DLUISTORE':lambda:True,'EL:DLUIFILL':lambda:None,'EL:DLUISTATUS':messages.append,
                'EL:DLUIASSETREADY':lambda *args:True})
            self.call('EL:DLUISetDraft',self.entry()); self.call('EL:DLUISaveWork')
            self.assertEqual(self.get('revision',self.get('catalog',self.call('EL:DLSnapshotLoad',root))),1)
            self.call('EL:DLUIChangeStatus',True)
            self.assertEqual(self.get('status',self.call('EL:DLUIEntry')),Symbol('DELETED'))
            self.call('EL:DLUIChangeStatus',None)
            self.assertEqual(self.get('status',self.call('EL:DLUIEntry')),Symbol('READY'))
            self.call('EL:DLUISetDraft',self.put('watts-text','invalid',self.call('EL:DLUIEntry')))
            self.call('EL:DLUIRefresh')
            self.assertEqual(self.get('watts-text',self.call('EL:DLUIEntry')),'invalid')

    def test_dcl_keys_callbacks_and_cancel_preserve_store(self):
        root=Path(__file__).resolve().parents[1]
        code=(root/'src/device-ui.lsp').read_text(encoding='utf-8')
        ui=(root/'ui/device-library.dcl').read_text(encoding='utf-8')
        keys=set(re.findall(r'key\s*=\s*"([^"]+)"',ui))
        used=set(re.findall(r'\((?:action_tile|set_tile|get_tile|start_list|mode_tile)\s+"([^"]+)"',code))
        self.assertTrue(used <= keys,used-keys)
        for line in code.splitlines():
            if '(action_tile' in line:
                for form in parse(line):
                    if isinstance(form,list) and form[0] == Symbol('ACTION_TILE'): self.assertTrue(parse(form[2]))
        self.assertEqual(ui.count('{'),ui.count('}'))
        self.assertIn('(EL:DLUIStore) (done_dialog 0)',code)

    def test_rename_keeps_old_name_by_default_and_can_be_disabled(self):
        self.cat=self.call('EL:DLUpsert',self.cat,self.entry('Old Lamp'))
        self.state()
        draft=self.put('block-name','New Lamp',self.get('devices',self.cat)[0])
        entry=self.call('EL:DLUIToEntry',draft)
        self.assertEqual(self.get('aliases',entry),['Old Lamp'])
        entry=self.call('EL:DLUIToEntry',self.put('keep-old-name',None,draft))
        self.assertFalse(truth(self.get('aliases',entry)))

    def test_missing_asset_cannot_publish_ready_or_restore_active(self):
        self.cat=self.call('EL:DLUpsert',self.cat,self.entry())
        self.cat=self.call('EL:DLDelete',self.cat,'ELDEV1')
        self.h.builtins['EL:DLUIASSETREADY']=lambda *args:None
        snapshot=[Pair(Symbol('CATALOG'),self.cat)]
        restored=self.call('EL:DLUIRestore',snapshot,'ELDEV1')
        row=self.get('devices',restored)[0]
        self.assertEqual(self.get('status',row),Symbol('DRAFT'))
        self.assertFalse(truth(self.get('active',row)))
        self.assertEqual(self.get('block-file',row),'assets/ELDEV1/1/block.dwg')

    def test_invalid_directory_never_changes_active_library_or_drafts(self):
        self.state();self.call('EL:DLUISetDraft',self.put('watts-text','7',self.entry()))
        before=self.h.lookup('*EL:DLUISTATE*')
        self.h.builtins.update({'VL-FILENAME-DIRECTORY':lambda _: '/other',
            'EL:DLSNAPSHOTLOAD':lambda _:None,
            'EL:DLROOTSET':lambda *_:self.fail('invalid target must not publish the preference')})
        self.assertFalse(truth(self.call('EL:DLUISwitchRoot','/other/catalog.eld')))
        self.assertEqual(self.h.lookup('*EL:DLUISTATE*'),before)


if __name__=='__main__':unittest.main()
