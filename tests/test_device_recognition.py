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

    def test_saved_library_values_do_not_follow_later_edit_until_explicit_apply(self):
        result,powers,snap=self.model(('Lamp',))
        old=self.get('devices',self.cat)[0]
        new_cat=self.call('EL:DLUpsert',self.cat,self.put('watts',9,self.put('is-ground',True,old)))
        new_snap=self.put('catalog',new_cat,self.put('index',self.call('EL:DLIndex',new_cat),snap))
        preserved=self.call('EL:DLPrepare',result,powers,new_snap,None)
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',preserved)),5)
        self.assertFalse(truth(self.get('is-ground',self.get('circuits',self.call('EL:DLGround',self.get('result',preserved)))[0])))
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


if __name__=='__main__':unittest.main()
