"""Name-based defaults, overrides and material rows. Date: 2026-10-11."""
from pathlib import Path
import tempfile
import unittest
import test_device_library as backend
from autolisp_host import Pair, Symbol, truth
from test_diagram_store import dump


class DeviceRecognitionTests(unittest.TestCase):
    setUp = backend.DeviceLibraryTests.setUp
    call = backend.DeviceLibraryTests.call
    get = backend.DeviceLibraryTests.get
    put = backend.DeviceLibraryTests.put
    entry = backend.DeviceLibraryTests.entry
    add = backend.DeviceLibraryTests.add
    fs = backend.DeviceLibraryTests.fs

    def model(self, names=('Lamp','Old Lamp'), ground=None):
        self.add(self.put('aliases',['Old Lamp'],self.entry('Lamp', ground=ground)))
        snapshot=[Pair(Symbol('ROOT'),'library/'),Pair(Symbol('CATALOG'),self.cat),Pair(Symbol('INDEX'),self.call('EL:DLIndex',self.cat))]
        self.h.set('*EL:DLSESSIONSNAPSHOT*',snapshot)
        blocks=[]
        for i,name in enumerate(names):
            blocks.append([Pair(Symbol('ID'),f'D{i}'),Pair(Symbol('NAME'),name),Pair(Symbol('ROLE'),Symbol('DEVICE')),
                           Pair(Symbol('IDENTITY'),[name,None,'block-name-v1'])])
        result=self.h.run("'((engine . fixed) (panel . \"P1\") (complete . T) (snapshot) (circuits ((id . \"C1\") (complete . T) (ground-source . default))))")
        result=self.put('snapshot',[Pair(Symbol('BLOCKS'),blocks),Pair(Symbol('SIGNATURE'),'unchanged-source')],result)
        c=self.get('circuits',result)[0]
        result=self.put('circuits',[self.put('devices',[f'D{i}' for i in range(len(names))],c)],result)
        prepared=self.call('EL:DLPrepare',result,None,snapshot,None)
        return self.get('result',prepared),self.get('powers',prepared),snapshot

    def test_aliases_merge_device_id_and_count_actual_ids_without_changing_source(self):
        result,powers,_=self.model()
        rows=self.call('EL:DLMaterialRows',result,powers)
        self.assertEqual(len(rows),1)
        self.assertEqual(self.get('count',rows[0]),2)
        self.assertEqual(sorted(self.get('ids',rows[0])),['D0','D1'])
        self.assertEqual(self.get('display',rows[0]),'应急灯 "A"\\样例')
        computed=self.call('EL:PanelCompute',result,powers,None)
        self.assertEqual(self.get('box-watts',computed),10)
        self.assertTrue(truth(self.get('can-generate',computed)))
        self.assertEqual(self.get('signature',self.get('snapshot',computed)),'unchanged-source')

    def test_unknown_block_is_retained_and_cannot_be_silently_zero_or_non_ground(self):
        result,powers,_=self.model(('Unknown',))
        computed=self.call('EL:PanelCompute',result,powers,None)
        self.assertFalse(truth(self.get('can-generate',computed)))
        row=self.call('EL:DLMaterialRows',computed,powers)[0]
        self.assertEqual(self.get('ids',row),['D0'])
        self.assertIsNone(self.get('watts',row));self.assertFalse(truth(self.get('ground-known',row)))
        self.assertEqual(self.get('library-pending',computed),['UNKNOWN'])

    def test_unknown_local_manual_zero_and_explicit_false_ground_are_supported(self):
        result,powers,_=self.model(('Unknown',))
        for key,value in [('watts',0),('watts-set',True),('is-ground',None),('ground-set',True)]:
            result=self.call('EL:DLSetOverride',result,'Unknown',Symbol(key.upper()),value)
        powers=self.call('EL:Put','UNKNOWN',0,powers)
        computed=self.call('EL:PanelCompute',result,powers,None)
        self.assertTrue(truth(self.get('can-generate',computed)))
        self.assertFalse(truth(self.get('is-ground',self.get('circuits',computed)[0])))

    def test_power_only_manual_confirmation_cannot_infer_false_ground(self):
        result,powers,_=self.model(('Unknown',))
        result=self.call('EL:DLSetOverride',result,'Unknown',Symbol('WATTS-SET'),True)
        powers=self.call('EL:Put','UNKNOWN',5,powers)
        computed=self.call('EL:PanelCompute',result,powers,None)
        self.assertFalse(truth(self.get('can-generate',computed)))

    def test_marked_defaults_refresh_only_on_recognition_and_manual_values_survive(self):
        result,powers,snap=self.model(('Lamp',))
        old=self.get('devices',self.cat)[0]
        new_cat=self.call('EL:DLUpsert',self.cat,self.put('watts',9,self.put('is-ground',True,old)))
        new_snap=self.put('catalog',new_cat,self.put('index',self.call('EL:DLIndex',new_cat),snap))
        preserved=self.call('EL:DLPrepare',result,powers,new_snap,None)
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',preserved)),9)
        self.assertTrue(truth(self.get('is-ground',self.get('circuits',self.call('EL:DLGround',self.get('result',preserved)))[0])))
        self.assertEqual(self.call('EL:Get','LAMP',powers),5)  # Previously displayed/saved input is immutable.
        updated=self.call('EL:DLPrepare',result,powers,new_snap,True)
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',updated)),9)
        self.assertTrue(truth(self.get('is-ground',self.get('circuits',self.call('EL:DLGround',self.get('result',updated)))[0])))

    def test_manual_watts_and_circuit_false_ground_override_catalog_defaults(self):
        result,powers,snap=self.model(('Lamp',),ground=True)
        result=self.call('EL:DLSetOverride',result,'Lamp',Symbol('WATTS'),0)
        result=self.call('EL:DLSetOverride',result,'Lamp',Symbol('WATTS-SET'),True)
        c=self.get('circuits',result)[0]
        result=self.put('circuits',[self.put('ground-source',Symbol('MANUAL'),self.put('is-ground',None,c))],result)
        prepared=self.call('EL:DLPrepare',result,powers,snap,None)
        computed=self.call('EL:PanelCompute',self.get('result',prepared),self.get('powers',prepared),None)
        self.assertEqual(self.get('box-watts',computed),0)
        self.assertTrue(truth(self.get('can-generate',computed)))
        self.assertFalse(truth(self.get('is-ground',self.get('circuits',computed)[0])))

    def test_manual_different_watts_or_ground_split_same_device_material_rows(self):
        result,powers,_=self.model()
        result=self.call('EL:DLSetOverride',result,'Old Lamp',Symbol('IS-GROUND'),True)
        result=self.call('EL:DLSetOverride',result,'Old Lamp',Symbol('GROUND-SET'),True)
        powers=self.call('EL:Put','OLD LAMP',7,powers)
        rows=self.call('EL:DLMaterialRows',result,powers)
        self.assertEqual(len(rows),2)
        self.assertEqual(sorted(self.get('watts',r) for r in rows),[5,7])

    def test_dwg_native_codec_preserves_library_snapshot_manual_false_and_zero(self):
        result,powers,_=self.model()
        result=self.call('EL:DLSetOverride',result,'Lamp',Symbol('WATTS'),0)
        result=self.call('EL:DLSetOverride',result,'Lamp',Symbol('WATTS-SET'),True)
        record=self.call('EL:DLPersist',result,self.h.run("'((source-panel-handle . \"P1\"))"))
        store=self.put('diagrams',[record],self.h.run("'((schema-version . 1) (drawing-uuid . \"D\") (diagrams))"))
        self.assertEqual(self.call('EL:StoreDecode',self.call('EL:StoreEncode',store)),store)
        restored=self.call('EL:DLRestoreRecord',self.put('device-library',None,result),record)
        self.assertEqual(self.get('device-overrides',restored),self.get('device-overrides',record))

    def test_damaged_library_blocks_submission_instead_of_falling_back_to_defaults(self):
        result,powers,_=self.model()
        prepared=self.call('EL:DLPrepare',result,powers,None,None)
        computed=self.call('EL:PanelCompute',self.get('result',prepared),self.get('powers',prepared),None)
        self.assertFalse(truth(self.get('can-generate',computed)))

    def test_command_snapshot_loads_once_but_submit_checks_actual_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.fs(d)
            self.h.builtins['EL:DLROOT']=lambda:root
            self.h.builtins['GETVAR']=lambda key:100
            self.call('EL:PerfStart','ELSTAT')
            first=self.call('EL:DLSnapshot');self.assertEqual(first,self.call('EL:DLSnapshot'))
            self.assertEqual(self.call('EL:Get','device-library-loads',self.h.lookup('*EL:PERFMETRICS*')),1)
            Path(d,'catalog.eld').write_text(dump(self.cat),encoding='utf-8')
            self.assertFalse(truth(self.call('EL:DLSnapshotCurrent',first)))

    def test_local_utf8_cache_exact_roundtrip_and_no_implicit_catalog_write(self):
        with tempfile.TemporaryDirectory() as d:
            self.fs(d)
            path=str(Path(d,'manual.eld'))
            data=self.h.run("'((schema . EL_DEVICE_INPUTS_V1) (powers (\"灯具\" . 0)) (device-overrides (\"灯具\" (watts . 0) (watts-set . T) (is-ground) (ground-set . T))))")
            self.assertTrue(truth(self.call('EL:DLInputsPublish',path,data)))
            self.assertEqual(self.call('EL:StoreParse',Path(path).read_text(encoding='utf-8')),data)
            self.assertFalse(Path(d,'catalog.eld').exists())

    def test_legacy_box_cache_is_manual_and_current_window_values_win(self):
        result,powers,snapshot=self.model(names=('Lamp',))
        raw=self.h.run("'((engine . fixed) (panel . \"P1\"))")
        record=self.h.run("'((source-panel-handle . \"P1\") (powers (\"LAMP\" . 5)) (block-ground (\"LAMP\")))")
        self.h.builtins['EL:DLLOADINPUTS']=lambda _:None
        self.h.builtins['EL:DlLegacyInputs'.upper()]=lambda _: self.h.run("'((version . 1) (powers (\"LAMP\" . 0)))")
        restored=self.call('EL:DLRestoreRecord',raw,record)
        self.assertEqual(self.get('watts',self.call('EL:DLOverride','Lamp',restored)),0)
        self.assertTrue(truth(self.get('ground-set',self.call('EL:DLOverride','Lamp',restored))))
        self.assertFalse(truth(self.get('is-ground',self.call('EL:DLOverride','Lamp',restored))))
        current=self.call('EL:DLSetOverride',restored,'Lamp',Symbol('WATTS'),7)
        restored=self.call('EL:DLRestoreRecord',current,record)
        self.assertEqual(self.get('watts',self.call('EL:DLOverride','Lamp',restored)),7)

    def test_external_catalog_change_refreshes_defaults_and_keeps_dialog_open(self):
        result,powers,snapshot=self.model(names=('Lamp',))
        newer=self.put('watts',9,self.get('devices',self.cat)[0])
        newer=self.call('EL:DLUpsert',self.cat,newer)
        fresh=[Pair(Symbol('ROOT'),'library/'),Pair(Symbol('CATALOG'),newer),Pair(Symbol('INDEX'),self.call('EL:DLIndex',newer))]
        messages=[]
        self.h.builtins.update({'EL:DLSNAPSHOTCURRENT':lambda _:None,'EL:DLROOT':lambda:'library/',
            'EL:DLSNAPSHOTLOAD':lambda _:fresh,'EL:THUMBPREPARE':lambda _:None,'EL:PANELFILL':lambda:None,
            'EL:PANELTEXT':lambda key,value:messages.append(value),'DONE_DIALOG':lambda *_:self.fail('must stay open')})
        self.h.set('*EL:PANELDRAFT*',result);self.h.set('*EL:PANELPOWERS*',powers)
        self.assertFalse(truth(self.call('EL:DLPanelSubmissionReady')))
        self.assertEqual(self.call('EL:Get','LAMP',self.h.lookup('*EL:PANELPOWERS*')),9)
        self.assertIn('库默认值已刷新',messages[-1])
        manual=self.call('EL:DLSetOverride',result,'Lamp',Symbol('WATTS'),0)
        manual=self.call('EL:DLSetOverride',manual,'Lamp',Symbol('WATTS-SET'),True)
        self.h.set('*EL:PANELDRAFT*',manual)
        self.call('EL:DLPanelSubmissionReady')
        self.assertEqual(self.call('EL:Get','LAMP',self.h.lookup('*EL:PANELPOWERS*')),0)

    def test_explicit_same_watts_entry_becomes_manual_and_survives_later_default_change(self):
        result,powers,snapshot=self.model(names=('Lamp',))
        self.h.set('*EL:PANELDRAFT*',result);self.h.set('*EL:PANELPOWERS*',powers);self.h.set('*EL:THUMBPAGE*',0)
        self.h.builtins.update({'GET_TILE':lambda _: '5','EL:PANELFILL':lambda:None,
            'EL:REMEMBERPANELPOWERS':lambda *args:True,'EL:PANELTEXT':lambda *args:None})
        self.call('EL:PanelBlockPowerChanged',0)
        result=self.h.lookup('*EL:PANELDRAFT*')
        self.assertTrue(truth(self.get('watts-set',self.call('EL:DLOverride','Lamp',result))))
        newer=self.call('EL:DLUpsert',self.cat,self.put('watts',9,self.get('devices',self.cat)[0]))
        snapshot=self.put('index',self.call('EL:DLIndex',newer),self.put('catalog',newer,snapshot))
        prepared=self.call('EL:DLPrepare',result,powers,snapshot,None)
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',prepared)),5)

    def test_unknown_reference_does_not_change_with_empty_library_identity(self):
        result,powers,snapshot=self.model(names=('Unknown',))
        first=self.call('EL:DLPrepare',result,powers,snapshot,None)
        empty=self.put('catalog',self.call('EL:DLCatalogInitial','EMPTY-OTHER'),self.put('index',None,snapshot))
        second=self.call('EL:DLPrepare',self.get('result',first),self.get('powers',first),empty,None)
        self.assertEqual(self.get('device-library',self.get('result',first)),self.get('device-library',self.get('result',second)))

    def test_historical_snapshot_cannot_supply_new_instances_after_switching_library(self):
        result,powers,snapshot=self.model(names=('Lamp',))
        newcat=self.call('EL:DLUpsert',self.call('EL:DLCatalogInitial','OTHER-LIB'),self.entry('Lamp',watts=9))
        snapshot=self.put('index',self.call('EL:DLIndex',newcat),self.put('catalog',newcat,snapshot))
        old=self.call('EL:DLPrepare',result,powers,snapshot,None)
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',old)),5)
        blocks=self.get('blocks',self.get('snapshot',result))
        blocks=blocks+[self.put('id','NEW',blocks[0])]
        result=self.put('snapshot',self.put('blocks',blocks,self.get('snapshot',result)),result)
        circuit=self.put('devices',['D0','NEW'],self.get('circuits',result)[0])
        result=self.put('circuits',[circuit],result)
        current=self.call('EL:DLPrepare',result,powers,snapshot,None)
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',current)),9)

    def test_legacy_box_cache_is_found_in_previous_runtime_and_never_rewritten(self):
        with tempfile.TemporaryDirectory() as d:
            self.fs(d);parent=Path(d,'Emergency-Lighting');old=parent/'runtime-095/config';old.mkdir(parents=True)
            source=old/'power-input-key.eld';source.write_text('( (version . 1) (powers ("LAMP" . 7)))',encoding='utf-8')
            original=source.read_bytes()
            self.h.builtins.update({'EL:POWERINPUTPATH':lambda _:str(parent/'runtime-096/config/power-input-key.eld'),
                'VL-FILENAME-BASE':lambda p:Path(p).stem,'GETENV':lambda _:d,'VL-REGISTRY-READ':lambda *args:None,
                'VL-DIRECTORY-FILES':lambda *args:['runtime-095','runtime-096'],'VL-FILE-SIZE':lambda p:Path(p).stat().st_size,
                'EL:READDATA':lambda p:self.call('EL:StoreParse',Path(p).read_text(encoding='utf-8'))})
            data=self.call('EL:DLLegacyInputs','P1')
            self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',data)),7)
            self.assertEqual(source.read_bytes(),original)

    def test_advanced_identity_power_records_keep_original_shape_and_skip_name_caches(self):
        result=self.h.run("'((panel . \"P1\") (circuits))")
        record=self.h.run("'((powers ((identity \"Lamp\" nil \"identity-v2\") (category . lighting) (watts . 5))))")
        self.h.builtins['EL:DLLOADINPUTS']=lambda *_:self.fail('advanced flow must use its original identity values')
        self.assertEqual(self.call('EL:DLRestoreRecord',result,record),result)
        self.assertFalse(truth(self.get('device-overrides',result)))


if __name__=='__main__':unittest.main()
