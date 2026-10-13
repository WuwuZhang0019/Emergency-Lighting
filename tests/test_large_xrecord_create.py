"""Large XRecord creation and interrupted-save checks. Date: 2026-10-13.
ENTMAKEX bounds below are conservative adapter fault injection, not measured CAD limits.
"""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_diagram_store as db


class LargeXRecordTests(unittest.TestCase):
    def setUp(self):
        self.f=db.StoreTests()
        self.f.setUp()
        self.h=self.f.h
        self.h.frames[0]['*EL:LOGACTIVE*']=True
        self.events=[]
        self.h.builtins['EL:LOGEVENT']=lambda stage,context:self.events.append((stage,context))
        create=self.h.builtins['ENTMAKEX']
        self.created_sizes=[]
        def bounded(data):
            self.created_sizes.append(len(data))
            if len(data)>1024:
                raise RuntimeError('native creation fault: oversized ENTMAKEX argument')
            return create(data)
        self.h.builtins['ENTMAKEX']=bounded

    def call(self,name,*args):
        return self.h.call(Symbol(name.upper()),list(args))

    def get(self,key,row):
        return self.call('EL:Get',Symbol(key.upper()),row)

    def large_store(self):
        # Long native REAL tape plus nontrivial strings; use the actual compact codec.
        return self.call('EL:Put',Symbol('MEASUREMENTS'),[float(i)+1.e-10 for i in range(1800)],
            self.call('EL:Put',Symbol('NOTES'),'中文图纸保存\\原样\n'*300,self.call('EL:StoreInitial')))

    def test_first_large_store_save_reopen_and_rewrite_preserve_exact_contents(self):
        store=self.large_store()
        self.assertTrue(truth(self.call('EL:StoreWrite',store)))
        self.assertEqual(self.call('EL:StoreRead'),store)
        entity=self.f.dictionary['EL_FIXED_V1']
        changed=self.call('EL:Put',Symbol('NOTES'),'改写仍保留完整测量值',store)
        self.assertTrue(truth(self.call('EL:StoreWrite',changed)))
        self.assertEqual(self.f.dictionary['EL_FIXED_V1'],entity)
        self.assertEqual(self.call('EL:StoreRead'),changed)
        self.assertLessEqual(max(self.created_sizes),1024)
        stages=[stage for stage,_ in self.events]
        for stage in ('ENTER STORE_PREWRITE_COMPARE','LEAVE STORE_PREWRITE_COMPARE',
                      'ENTER STORE_CREATE_PAYLOAD','LEAVE STORE_CREATE_PAYLOAD',
                      'ENTER STORE_REPLACE_PAYLOAD','LEAVE STORE_REPLACE_PAYLOAD','ENTER STORE_READBACK'):
            self.assertIn(stage,stages)

    def test_219138_native_fields_use_small_header_and_exact_typed_payload(self):
        # Match the supplied log's field count without inventing original DWG contents.
        chunks=[Pair(300,'EL_TYPED_V1'),Pair(2,'L')]+[
            Pair(40,float(i)+1.e-20) for i in range(219135)]+[Pair(2,'E')]
        self.assertEqual(len(chunks),219138)
        entity=self.call('EL:StoreCreatePayload',chunks,1)
        self.h.builtins['DICTADD']('NOD','EL_FIXED_V1',entity)
        entry=self.h.builtins['DICTSEARCH']('NOD','EL_FIXED_V1')
        native=self.h.builtins['ENTGET'](entity)
        self.assertEqual(self.call('EL:StoreAuditPayload',chunks,entry,Symbol('DICTSEARCH')),chunks)
        self.assertEqual(self.call('EL:StoreAuditPayload',chunks,native,Symbol('ENTGET')),chunks)
        self.assertEqual(self.created_sizes,[3])

    def test_large_legacy_backup_also_avoids_payload_in_entmakex(self):
        store=self.large_store()
        historical=[Pair(0,'XRECORD'),Pair(100,'AcDbXrecord'),Pair(280,2)]+self.call('EL:StoreEncodeLegacy',store)
        self.assertGreater(len(historical),1024)
        # Seed historical data before applying the constructor fault boundary.
        self.f.entities['legacy']=[Pair(-1,'legacy'),Pair(5,'legacy')]+historical
        self.f.dictionary['EL_FIXED_V1']='legacy'
        self.f.install_transaction()
        self.h.frames[0]['STORE']=store
        self.assertTrue(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertEqual(self.call('EL:StoreRead'),store)
        backup=self.f.dictionary['EL_FIXED_V1_LEGACY']
        self.assertEqual(self.get('notes',self.call('EL:StoreLegacyBackupVerify',
            self.call('EL:StorePayload',self.f.entities[backup]),backup,store)),self.get('notes',store))
        self.assertEqual(next(p.cdr for p in self.f.entities[backup] if p.car==280),2)
        self.assertEqual(self.f.dictionary['EL_FIXED_V1'],'legacy')
        self.assertLessEqual(max(self.created_sizes),1024)

    def test_native_write_failure_rolls_back_new_header_and_logs_stage(self):
        self.f.install_transaction()
        self.h.frames[0]['STORE']=self.large_store()
        self.h.frames[0]['*EL:LOGACTIVE*']=True
        self.h.builtins['VLA-SETXRECORDDATA']=lambda *args:(_ for _ in ()).throw(RuntimeError('native payload write failed'))
        before=(dict(self.f.entities),dict(self.f.dictionary))
        self.assertFalse(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertEqual((self.f.entities,self.f.dictionary),before)
        error=next(ctx for stage,ctx in self.events if stage=='TRANSACTION_ERROR')
        self.assertIn('native payload write failed',self.get('message',error))
        self.assertIn('STORE_REPLACE_PAYLOAD',str(self.get('stack',error)))

    def test_log_records_compare_failure_before_native_write(self):
        self.f.install_transaction()
        self.h.frames[0]['STORE']=self.large_store()
        self.h.frames[0]['*EL:LOGACTIVE*']=True
        self.h.builtins['EL:STORECHECK']=lambda *args:(_ for _ in ()).throw(RuntimeError('pre-write equality failed'))
        self.assertFalse(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        error=next(ctx for stage,ctx in self.events if stage=='TRANSACTION_ERROR')
        self.assertIn('STORE_PREWRITE_COMPARE',str(self.get('stack',error)))
        self.assertNotIn('EL_FIXED_V1',self.f.dictionary)

    def test_large_native_readback_corruption_is_rejected_and_rolled_back(self):
        self.f.install_transaction()
        self.h.frames[0]['STORE']=self.large_store()
        replace=self.h.builtins['VLA-SETXRECORDDATA']
        def corrupt(entity,codes,values):
            items=list(values['values'])
            index=next(i for i,code in enumerate(codes['values']) if code==40)
            kind,vt,value=items[index]
            items[index]=(kind,vt,value+1.e-6)
            return replace(entity,codes,dict(values,values=items))
        self.h.builtins['VLA-SETXRECORDDATA']=corrupt
        self.assertFalse(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertNotIn('EL_FIXED_V1',self.f.dictionary)
        self.assertFalse(self.f.entities)
        self.assertIn('STORE_DXF_MISMATCH',[stage for stage,_ in self.events])

    def test_large_dictionary_attach_failure_rolls_back_written_payload(self):
        self.f.install_transaction()
        self.h.frames[0]['STORE']=self.large_store()
        attach=self.h.builtins['DICTADD']
        self.h.builtins['DICTADD']=lambda nod,key,entity:None if key=='EL_FIXED_V1' else attach(nod,key,entity)
        self.assertFalse(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertNotIn('EL_FIXED_V1',self.f.dictionary)
        self.assertFalse(self.f.entities)
        self.assertIn('ENTER STORE_DICT_ATTACH',[stage for stage,_ in self.events])
