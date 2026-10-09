"""DWG record adapter checks; no native CAD acceptance. Date: 2026-10-09."""
import pathlib
import unittest
from autolisp_host import Host, Pair, Symbol, truth

ROOT=pathlib.Path(__file__).resolve().parents[1]
def dump(x):
    if x is None or x is False: return 'nil'
    if x is True: return 'T'
    if isinstance(x,Symbol): return str(x)
    if isinstance(x,Pair): return '('+dump(x.car)+' . '+dump(x.cdr)+')'
    if isinstance(x,list): return '('+' '.join(map(dump,x))+')'
    if isinstance(x,str): return '"'+x.replace('\\','\\\\').replace('"','\\"')+'"'
    return str(x)

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.h=Host()
        for name in ('common','diagram-store'):
            self.h.load_definitions(ROOT/'src'/f'{name}.lsp')
        self.entities={}; self.dictionary={}
        def create(data):
            e=str(len(self.entities)+1); self.entities[e]=[Pair(-1,e),Pair(5,e)]+data; return e
        def modify(data):
            e=next(p.cdr for p in data if p.car==-1); self.entities[e]=data; return e
        self.h.builtins.update({'VL-PRIN1-TO-STRING':dump,'NAMEDOBJDICT':lambda:'NOD',
          'DICTSEARCH':lambda _,key:self.entities.get(self.dictionary.get(key)),
          'DICTADD':lambda _,key,e:self.dictionary.setdefault(key,e),
          'ENTMAKEX':create,'ENTMOD':modify,'ENTGET':lambda e,*apps:self.entities.get(e),
          'HANDENT':lambda e:e if e in self.entities else None,
          'GETVAR':lambda name:'drawing-guid' if name=='FINGERPRINTGUID' else None})

    def test_chunked_xrecord_roundtrip_and_reopen(self):
        self.h.run('(setq store (EL:StoreInitial))')
        self.h.frames[0]['LONG']='中文'*500
        self.assertTrue(truth(self.h.run("(EL:StoreWrite (EL:Put 'notes long store))")))
        entry=self.entities[self.dictionary['EL_FIXED_V1']]
        self.assertTrue(all(len(p.cdr)<=100 for p in entry if p.car==1))
        self.h.run('(setq store nil)')
        self.assertEqual(self.h.run("(EL:Get 'notes (EL:StoreRead))"),'中文'*500)
        self.assertTrue(truth(self.h.run("(EL:StoreWrite (EL:Put 'notes \"changed\" (EL:StoreRead)))")))
        self.assertEqual(len(self.entities),1)

    def test_foreign_or_copied_handle_is_not_owned(self):
        self.h.run("(setq store (EL:StoreInitial) record '((diagram-id . \"diagram1\")))")
        tag=[Pair(1000,x) for x in ('drawing-guid','diagram1','text','uid1','A')]
        self.entities['A']=[Pair(0,'TEXT'),Pair(5,'A'),[-3,['EL_FIXED_V1']+tag]]
        self.assertEqual(self.h.run('(EL:OwnedEntity "A" store record "text" "uid1")'),'A')
        self.entities['B']=[Pair(0,'TEXT'),Pair(5,'B'),[-3,['EL_FIXED_V1']+tag]]
        self.assertFalse(truth(self.h.run('(EL:OwnedEntity "B" store record "text" "uid1")')))
        self.assertFalse(truth(self.h.run('(EL:OwnedEntity "A" store record "text" "uid2")')))
        self.assertTrue(truth(self.h.run('(EL:ManagedEntity "B")')))
