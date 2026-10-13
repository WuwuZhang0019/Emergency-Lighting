"""Fallback drawing identity on the CAD2020 byte engine. Date: 2026-10-13.
Adapter models CP936 byte slicing and native string conversion; native CAD pending.
"""
import copy
import unittest
from autolisp_host import Pair, Symbol, truth
import test_diagram_store as db


def encoded(text):
    return text.encode('cp936', errors='surrogateescape')


def decoded(raw):
    return raw.decode('cp936', errors='surrogateescape')


class FallbackUUIDTests(unittest.TestCase):
    def setUp(self):
        self.f=db.StoreTests()
        self.f.setUp()
        self.h=self.f.h
        self.native_strings=[]
        # The old 64-byte signature prefix ends with the lead byte of 施 (CA).
        title='商业综合体项目设计合同'+chr(92)+'一期'+chr(92)
        base='D:'+title
        padding=63-len(encoded(db.dump(base)[:-1]))
        self.path='D:'+'A'*padding+title+'施工图.dwg'
        signature=db.dump(self.path)
        self.assertEqual(encoded(signature)[63],0xca)
        self.old_prefix=decoded(encoded(signature)[:64])
        self.old_uuid='EL-20261013.12000000-6040-'+self.old_prefix
        self.h.builtins.update({
            'GETVAR':lambda key:{'CDATE':20261013.12,'MILLISECS':6040}.get(key),
            'EL:DRAWINGID':lambda:self.path,
            'STRLEN':lambda text:len(encoded(text)),
            'SUBSTR':lambda text,start,length=None:decoded(encoded(text)[start-1:] if length is None
                else encoded(text)[start-1:start-1+length]),
            'VL-STRING->LIST':lambda text:list(encoded(text)),
            'VL-LIST->STRING':lambda codes:decoded(bytes(codes or [])),
            'VL-STRING-MISMATCH':lambda a,b:next((i for i,(x,y) in enumerate(zip(encoded(a),encoded(b)))
                if x!=y),min(len(encoded(a)),len(encoded(b))))})
        create=self.h.builtins['ENTMAKEX']
        replace=self.h.builtins['VLA-SETXRECORDDATA']
        def native(text):
            self.native_strings.append(encoded(text))
            return encoded(text).decode('cp936',errors='replace').replace('\ufffd','?')
        self.h.builtins['ENTMAKEX']=lambda rows:create([
            Pair(p.car,native(p.cdr)) if isinstance(p.cdr,str) and not isinstance(p.cdr,Symbol) else p for p in rows])
        def setter(entity,codes,values):
            items=[(kind,vt,native(value) if vt==8 else value) for kind,vt,value in values['values']]
            return replace(entity,codes,dict(values,values=items))
        self.h.builtins['VLA-SETXRECORDDATA']=setter

    def call(self,name,*args):
        return self.h.call(Symbol(name.upper()),list(args))

    def get(self,key,row):
        return self.call('EL:Get',Symbol(key.upper()),row)

    def test_orphan_byte_reproduces_v118_readback_mismatch_and_rolls_back(self):
        self.f.install_transaction()
        store=self.call('EL:Put',Symbol('DRAWING-UUID'),self.old_uuid,self.call('EL:StoreInitial'))
        self.h.frames[0]['STORE']=store
        events=[]
        self.h.builtins['EL:LOGEVENT']=lambda stage,context:events.append((stage,context))
        self.assertFalse(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertEqual((self.f.entities,self.f.dictionary),({},{}))
        mismatch=next(ctx for stage,ctx in events if stage=='STORE_MISMATCH')
        self.assertIn(Symbol('DRAWING-UUID'),self.get('path',mismatch))
        self.assertEqual(encoded(self.get('expected',mismatch))[-1],0xca)
        self.assertTrue(self.get('actual',mismatch).endswith('?'))

    def test_byte_64_chinese_path_generates_ascii_identity_and_saves_reopens_rewrites(self):
        self.f.install_transaction()
        store=self.call('EL:StoreInitial')
        identity=self.get('drawing-uuid',store)
        self.assertTrue(identity.isascii())
        self.assertEqual(identity,self.get('drawing-uuid',self.call('EL:StoreInitial')))
        self.h.frames[0]['STORE']=store
        self.assertTrue(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.h.frames[0]['*EL:FALLBACKDRAWINGUUID*']=None
        self.assertEqual(self.call('EL:StoreRead'),store)
        entity=self.f.dictionary['EL_FIXED_V1']
        changed=self.call('EL:Put',Symbol('NOTES'),'中文路径原样保存',store)
        self.assertTrue(truth(self.call('EL:StoreWrite',changed)))
        self.assertEqual(self.call('EL:StoreRead'),changed)
        self.assertEqual(self.f.dictionary['EL_FIXED_V1'],entity)
        for raw in self.native_strings:
            raw.decode('cp936',errors='strict')

    def test_same_cad_session_repairs_incomplete_cached_fallback_without_reload(self):
        self.h.frames[0]['*EL:FALLBACKDRAWINGUUID*']=self.old_uuid
        store=self.call('EL:StoreInitial')
        self.assertTrue(self.get('drawing-uuid',store).isascii())
        self.assertNotEqual(self.get('drawing-uuid',store),self.old_uuid)
        self.assertTrue(truth(self.call('EL:StoreWrite',store)))
        self.assertEqual(self.call('EL:StoreRead'),store)

    def test_complete_historical_cached_and_persisted_identities_remain_unchanged(self):
        identity='EL-old-商业综合体项目设计合同\\一期\\施工图'
        self.h.frames[0]['*EL:FALLBACKDRAWINGUUID*']=identity
        store=self.call('EL:StoreInitial')
        self.assertEqual(self.get('drawing-uuid',store),identity)
        self.assertTrue(truth(self.call('EL:StoreWrite',store)))
        self.h.frames[0]['*EL:FALLBACKDRAWINGUUID*']='EL-new-cache'
        before=copy.deepcopy((self.f.entities,self.f.dictionary))
        self.assertEqual(self.call('EL:StoreRead'),store)
        self.assertEqual((self.f.entities,self.f.dictionary),before)

    def test_fingerprint_guid_takes_precedence_over_incomplete_cache(self):
        getvar=self.h.builtins['GETVAR']
        self.h.builtins['GETVAR']=lambda key:'native-guid' if key=='FINGERPRINTGUID' else getvar(key)
        self.h.frames[0]['*EL:FALLBACKDRAWINGUUID*']=self.old_uuid
        self.assertEqual(self.get('drawing-uuid',self.call('EL:StoreInitial')),'native-guid')

    def test_complete_checker_distinguishes_byte_engine_and_unicode_engine(self):
        for text,valid in (('',True),('ASCII',True),('施工图',True),('A中文B',True),(self.old_uuid,False)):
            with self.subTest(text=repr(text)):
                self.assertEqual(truth(self.call('EL:StoreStringComplete',text)),valid)
        self.h.builtins['GETVAR']=lambda key:1 if key=='LISPSYS' else None
        self.h.builtins['VL-STRING->LIST']=lambda text:list(map(ord,text))
        self.assertTrue(truth(self.call('EL:StoreStringComplete','é')))


if __name__=='__main__':
    unittest.main()
