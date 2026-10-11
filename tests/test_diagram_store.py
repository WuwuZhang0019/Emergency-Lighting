"""DWG record adapter checks; no native CAD acceptance. Date: 2026-10-11."""
import pathlib
import copy
import math
import unittest
from autolisp_host import Host, Pair, Symbol, truth

ROOT=pathlib.Path(__file__).resolve().parents[1]
def dump(x):
    if x is None or x is False: return 'nil'
    if x is True: return 'T'
    if isinstance(x,Symbol): return str(x)
    if isinstance(x,Pair): return '('+dump(x.car)+' . '+dump(x.cdr)+')'
    if isinstance(x,list): return '('+' '.join(map(dump,x))+')'
    if isinstance(x,str):
        escapes={'\\':'\\\\','"':'\\"','\x1b':'\\e','\n':'\\n','\r':'\\r','\t':'\\t'}
        return '"'+''.join(escapes.get(c, f'\\{ord(c):03o}' if ord(c)<32 else c) for c in x)+'"'
    return str(x)

def install_bounded_read(host, limit=256):
    """Conservative adapter bound, not a measured native CAD limit."""
    original=host.builtins['READ']; sizes=[]
    def bounded(text):
        sizes.append(len(text.encode('gb2312')))
        if sizes[-1]>limit:
            raise RuntimeError('输入的字符串太长')
        return original(text)
    host.builtins['READ']=bounded
    return sizes

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.h=Host()
        for name in ('common','config','device-library','device-recognition','device-inputs','store-compact','diagram-store','diagram-update'):
            self.h.load_definitions(ROOT/'src'/f'{name}.lsp')
        self.entities={}; self.dictionary={}; self.xrecord_id=0
        def create(data):
            # Native handles do not overwrite a live entity after a deletion.
            self.xrecord_id+=1
            while str(self.xrecord_id) in self.entities: self.xrecord_id+=1
            e=str(self.xrecord_id); self.entities[e]=[Pair(-1,e),Pair(5,e)]+data; return e
        def modify(data):
            e=next(p.cdr for p in data if p.car==-1); self.entities[e]=data; return e
        def fill(array, values):
            self.assertEqual(len(array['values']),len(values))
            array['values']=list(values)
            return array
        def replace(entity, codes, values):
            self.assertEqual(codes['kind'],2)
            self.assertEqual(values['kind'],12)
            payload=[]
            for code,variant in zip(codes['values'],values['values']):
                expected=5 if code==40 else 3 if code==90 else 8
                self.assertEqual(variant[1],expected)
                payload.append(Pair(code,variant[2]))
            self.entities[entity]=[p for p in self.entities[entity]
                                   if p.car not in (1,2,3,40,90,300)]+payload
        self.h.builtins.update({'VL-PRIN1-TO-STRING':dump,'NAMEDOBJDICT':lambda:'NOD',
          'DICTSEARCH':lambda _,key:self.entities.get(self.dictionary.get(key)),
          'DICTADD':lambda _,key,e:self.dictionary.setdefault(key,e),
          'ENTMAKEX':create,'ENTMOD':modify,'ENTGET':lambda e,*apps:self.entities.get(e),
          'VLAX-ENAME->VLA-OBJECT':lambda e:e,
          'VLAX-MAKE-SAFEARRAY':lambda kind,bounds:{'kind':kind,'values':[None]*(bounds.cdr-bounds.car+1)},
          'VLAX-SAFEARRAY-FILL':fill,'VLAX-MAKE-VARIANT':lambda value,kind:('variant',kind,value),
          'VLA-SETXRECORDDATA':replace,
          'HANDENT':lambda e:e if e in self.entities else None,
          'GETVAR':lambda name:'drawing-guid' if name=='FINGERPRINTGUID' else None})

    def install_transaction(self):
        undo=[]
        getvar=self.h.builtins['GETVAR']
        def rollback(*args):
            self.assertEqual(args,('_.UNDO','1'))
            entities,dictionary=undo.pop()
            self.entities.clear(); self.entities.update(entities)
            self.dictionary.clear(); self.dictionary.update(dictionary)
        self.h.builtins.update({
            'VLAX-GET-ACAD-OBJECT':lambda:'acad',
            'VLA-GET-ACTIVEDOCUMENT':lambda _:'doc',
            'VLA-STARTUNDOMARK':lambda _:undo.append(copy.deepcopy((self.entities,self.dictionary))),
            'VLA-ENDUNDOMARK':lambda _:None,
            'COMMAND-S':rollback,'REDRAW':lambda:None,
            'DICTREMOVE':lambda _,key:self.dictionary.pop(key,None),
            'ENTDEL':lambda e:self.entities.pop(e,None) and e,
            'GETVAR':lambda name:1 if name=='UNDOCTL' else getvar(name),
            'EXIT':lambda:(_ for _ in ()).throw(RuntimeError('LISP exit'))})

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

    def test_native_field_mutation_is_logged_before_decoder_exit(self):
        events=[]
        self.h.builtins['EL:LOGEVENT']=lambda stage,context:events.append((stage,context))
        create=self.h.builtins['ENTMAKEX']
        self.h.builtins['ENTMAKEX']=lambda data:create([
            Pair(2,'BROKEN') if p==Pair(2,'L') else p for p in data])
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:StoreWrite (EL:StoreInitial))')
        get=lambda key,row:self.h.call(Symbol('EL:GET'),[Symbol(key.upper()),row])
        diffs=[row for stage,row in events if stage=='STORE_DXF_MISMATCH']
        self.assertEqual([get('source',row) for row in diffs],[Symbol('DICTSEARCH'),Symbol('ENTGET')])
        self.assertEqual(get('index',diffs[0]),2)
        self.assertEqual(get('value',get('expected',diffs[0])),'L')
        self.assertEqual(get('value',get('actual',diffs[0])),'BROKEN')
        error=next(row for stage,row in events if stage=='STORE_PARSE_ERROR')
        self.assertEqual(get('token-index',error),2)
        self.assertEqual(get('phase',error),Symbol('DWG-READ'))
        self.assertIn('STORE_DECODE_ERROR',[stage for stage,_ in events])

    def test_dictionary_only_extra_field_is_distinguished_from_entity_data(self):
        events=[]
        self.h.builtins['EL:LOGEVENT']=lambda stage,context:events.append((stage,context))
        search=self.h.builtins['DICTSEARCH']
        def decorated(nod,key):
            entry=search(nod,key)
            return [Pair(3,'dictionary-envelope')]+entry if entry else None
        self.h.builtins['DICTSEARCH']=decorated
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:StoreWrite (EL:StoreInitial))')
        get=lambda key,row:self.h.call(Symbol('EL:GET'),[Symbol(key.upper()),row])
        diffs=[row for stage,row in events if stage=='STORE_DXF_MISMATCH']
        self.assertEqual(len(diffs),1)
        self.assertEqual(get('source',diffs[0]),Symbol('DICTSEARCH'))
        self.assertEqual(get('index',diffs[0]),1)
        reads=[row for stage,row in events if stage=='STORE_DXF_READBACK']
        self.assertTrue(truth(get('equal',reads[-1])))

    def test_schema_and_parse_errors_are_separate_and_diagnostics_are_bounded(self):
        events=[]
        self.h.builtins['EL:LOGEVENT']=lambda stage,context:events.append((stage,context))
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:StoreWrite \'((schema-version . 9)))')
        self.assertIn('STORE_SCHEMA_ERROR',[stage for stage,_ in events])
        self.assertNotIn('STORE_DECODE_ERROR',[stage for stage,_ in events])
        summary=self.h.call(Symbol('EL:STORETOKENSUMMARY'),[Pair(1,'x'*10000)])
        get=lambda key:self.h.call(Symbol('EL:GET'),[Symbol(key),summary])
        self.assertEqual(get('LENGTH'),10000)
        self.assertEqual(len(get('VALUE')),96)

    def test_large_signature_save_reopen_and_rewrite_with_bounded_read(self):
        sizes=install_bounded_read(self.h)
        signature=('中文图层 C:\\项目\\图纸 "2223"\n'*4000)
        self.assertGreater(len(dump(signature)), 87345)
        self.h.frames[0]['SIGNATURE']=signature
        self.h.run("(setq store (EL:Put 'source-signature signature (EL:StoreInitial)))")
        self.assertTrue(truth(self.h.run('(EL:StoreWrite store)')))
        self.assertEqual(self.h.run("(EL:Get 'source-signature (EL:StoreRead))"),signature)
        self.assertTrue(truth(self.h.run("(EL:StoreWrite (EL:Put 'notes \"changed\" (EL:StoreRead)))")))
        self.assertEqual(self.h.run("(EL:Get 'source-signature (EL:StoreRead))"),signature)
        self.assertLessEqual(max(sizes),256)
        self.assertEqual(len(self.entities),1)

    def test_large_list_of_short_atoms_roundtrips_without_tail_recursion(self):
        sizes=install_bounded_read(self.h)
        rows=[[Pair(Symbol('HANDLE'),f'{i:04X}'),[Symbol('POSITION'),1251960.+i,401957.,0.]]
              for i in range(1500)]
        self.h.frames[0]['ROWS']=rows
        self.h.run("(setq store (EL:Put 'snapshot rows (EL:StoreInitial)))")
        self.assertGreater(len(self.h.run('(EL:StoreText store)')),87345)
        self.assertTrue(truth(self.h.run('(EL:StoreWrite store)')))
        self.assertEqual(self.h.run("(EL:Get 'snapshot (EL:StoreRead))"),rows)
        self.assertLessEqual(max(sizes),256)

    def test_legacy_large_v1_xrecord_reopens_without_format_migration(self):
        sizes=install_bounded_read(self.h)
        signature='历史中文图纸签名\\路径"块名" '*5000
        store=self.h.run('(EL:StoreInitial)')+[Pair(Symbol('SOURCE-SIGNATURE'),signature)]
        text=dump(store)
        self.assertGreater(len(text),87345)
        entity=self.h.builtins['ENTMAKEX']([Pair(0,'XRECORD')]+[Pair(1,text[i:i+100]) for i in range(0,len(text),100)])
        self.dictionary['EL_FIXED_V1']=entity
        before=copy.deepcopy((self.entities,self.dictionary))
        self.assertEqual(self.h.run('(EL:StoreRead)'),store)
        self.assertEqual((self.entities,self.dictionary),before)
        self.assertLessEqual(max(sizes),256)

    def test_string_escape_sequences_across_parser_boundaries(self):
        sizes=install_bounded_read(self.h)
        for prefix in range(92,101):
            with self.subTest(prefix=prefix):
                value='中文'+('a'*prefix)+'"\\\n\t\r\x1b\x00\x07\x1f'+('尾部'*120)
                self.assertEqual(self.h.call(Symbol('EL:STOREPARSE'),[dump(value)]),value)
        self.assertLessEqual(max(sizes),256)

    def test_parser_preserves_numbers_nil_symbols_and_improper_lists(self):
        sizes=install_bounded_read(self.h)
        value=self.h.run("'((real . -1.23456789012345) (zero . 0.0) (small . 0.0000001) (large . 1251960.125) (n . 42) (flag . T) (empty) (text . \"\") (tail a b . c))")
        self.assertEqual(self.h.call(Symbol('EL:STOREPARSE'),[self.h.call(Symbol('EL:STORETEXT'),[value])]),value)
        self.assertEqual(self.h.call(Symbol('EL:STOREPARSE'),['(.5 -1e-8)']),[.5,-1e-8])
        self.assertLessEqual(max(sizes),256)

    def test_parser_rejects_truncation_bad_pairs_and_trailing_data(self):
        for text in ('', '(a', '(a))', '( . a)', '(a . )', '(a . b c)', '(a . b . c)',
                     '"unfinished', '"unfinished\\', '(a) nil', '(a ;comment)', '(a \'b)'):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                self.h.call(Symbol('EL:STOREPARSE'),[text])

    def test_corrupt_store_and_serialization_mismatch_never_modify_dwg(self):
        self.h.run('(EL:StoreWrite (EL:StoreInitial))')
        before=copy.deepcopy((self.entities,self.dictionary))
        self.h.builtins['EL:STOREENCODE']=lambda _: [Pair(300,'EL_TYPED_V1'),Pair(2,'N')]
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:StoreWrite (EL:StoreInitial))')
        self.assertEqual((self.entities,self.dictionary),before)
        entity=self.dictionary['EL_FIXED_V1']
        self.entities[entity]=[Pair(1,'((schema-version . 1)')]
        before=copy.deepcopy((self.entities,self.dictionary))
        with self.assertRaises(RuntimeError):
            self.h.run('(EL:StoreRead)')
        self.assertEqual((self.entities,self.dictionary),before)

    def test_native_doubles_preserve_low_digits_tiny_values_and_signed_coordinates(self):
        # The old fixed-decimal codec loses these values before ENTMAKEX.
        reals=[0.12345678901234567, math.pi/36, 1e-20, -1e-20,
               math.nextafter(1251960.125, math.inf), -401957.123456789,
               0.0, 0.7, 1e99]
        self.assertNotEqual(self.h.call(Symbol('EL:STOREPARSE'),[
            self.h.call(Symbol('EL:STORETEXT'),[reals[0]])]),reals[0])
        self.h.frames[0]['REALS']=reals
        self.h.run("(setq store (EL:Put 'coordinates reals (EL:StoreInitial)))")
        self.h.builtins['RTOS']=lambda *args: self.fail('DWG persistence must not format doubles')
        self.assertTrue(truth(self.h.run('(EL:StoreWrite store)')))
        self.assertEqual(self.h.run("(EL:Get 'coordinates (EL:StoreRead))"),reals)
        entry=self.entities[self.dictionary['EL_FIXED_V1']]
        self.assertEqual([p.cdr for p in entry if p.car==40],reals)
        self.assertEqual(next(p.cdr for p in entry if p.car==300),'EL_COMPACT_TYPED_V2')

    def test_native_strings_bypass_printer_reader_escapes_and_keep_case(self):
        value='前缀 C:\\项目\\mixedCase\\图纸 "普通"\\U+4E2D\n\t\r'*3000
        self.h.frames[0]['TEXT']=value
        self.h.run("(setq store (EL:Put 'notes text (EL:StoreInitial)))")
        original_read=self.h.builtins['READ']
        self.h.builtins['READ']=lambda text: self.fail('strings must bypass READ') if text.startswith('"') else original_read(text)
        self.h.builtins['VL-PRIN1-TO-STRING']=lambda *args: self.fail('native storage must bypass printer')
        self.assertTrue(truth(self.h.run('(EL:StoreWrite store)')))
        self.assertEqual(self.h.run("(EL:Get 'notes (EL:StoreRead))"),value)

    def test_gb2312_byte_engine_never_splits_multibyte_strings_in_xrecord(self):
        # Deliberately use byte-based legacy helpers and reject partial GB2312
        # at ENTMAKEX/ENTMOD, independently of the Unicode host defaults.
        value=('a'*31+'中文路径\\ MixedCase "2223"\n')*50
        getvar=self.h.builtins['GETVAR']
        self.h.builtins.update({'GETVAR':lambda key:0 if key=='LISPSYS' else getvar(key),
            'VL-STRING->LIST':lambda text:list(text.encode('gb2312')),
            'VL-LIST->STRING':lambda codes:bytes(codes or []).decode('gb2312'),
            'STRLEN':lambda text:len(text.encode('gb2312'))})
        self.h.frames[0]['TEXT']=value
        self.assertTrue(truth(self.h.run("(EL:StoreWrite (EL:Put 'notes text (EL:StoreInitial)))")))
        entry=self.entities[self.dictionary['EL_FIXED_V1']]
        self.assertTrue(all(len(p.cdr.encode('gb2312'))<=33 for p in entry if p.car==1))
        self.assertEqual(self.h.run("(EL:Get 'notes (EL:StoreRead))"),value)

    def test_legacy_record_migrates_atomically_in_place_and_preserves_metadata(self):
        self.install_transaction()
        store=self.h.run('(EL:StoreInitial)')+[Pair(Symbol('NOTES'),'历史草稿 MixedCase')]
        text=dump(store)
        entity=self.h.builtins['ENTMAKEX']([Pair(0,'XRECORD'),Pair(100,'AcDbXrecord'),Pair(280,1),
             Pair(330,'NOD')]+[Pair(1,text[i:i+100]) for i in range(0,len(text),100)])
        self.dictionary['EL_FIXED_V1']=entity
        self.assertEqual(self.h.run('(EL:StoreRead)'),store)
        self.h.frames[0]['STORE']=store
        self.assertTrue(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertEqual(self.dictionary['EL_FIXED_V1'],entity)
        self.assertEqual(self.h.run('(EL:StoreRead)'),store)
        self.assertIn(Pair(330,'NOD'),self.entities[entity])
        self.assertIn(Pair(280,1),self.entities[entity])

    def test_74_legacy_fields_are_replaced_even_when_entmod_would_retain_them(self):
        self.install_transaction()
        store=self.h.run('(EL:StoreInitial)')+[Pair(Symbol('NOTES'),'')]
        store[-1]=Pair(Symbol('NOTES'),'x'*(7400-len(dump(store))))
        text=dump(store)
        self.assertEqual(len(text),7400)
        entity=self.h.builtins['ENTMAKEX']([Pair(0,'XRECORD'),Pair(100,'AcDbXrecord'),
            Pair(280,1),Pair(330,'NOD')]+[Pair(1,text[i:i+100]) for i in range(0,7400,100)])
        self.dictionary['EL_FIXED_V1']=entity
        calls=[]
        def retaining_entmod(data):
            calls.append(data)
            self.entities[entity]+=[p for p in data if p.car in (1,2,3,40,90,300)]
            return data
        self.h.builtins['ENTMOD']=retaining_entmod
        self.h.frames[0]['STORE']=store
        self.assertTrue(truth(self.h.run("(EL:Transaction 'EL:StoreWrite (list store))")))
        self.assertEqual(calls,[])
        self.assertEqual(self.h.run('(EL:StorePayload (dictsearch (namedobjdict) "EL_FIXED_V1"))'),
                         self.h.run('(EL:StoreEncode store)'))
        self.assertEqual(self.h.run('(EL:StoreRead)'),store)
        self.assertEqual(self.dictionary['EL_FIXED_V1'],entity)

    def test_typed_decoder_rejects_missing_end_wrong_types_and_unknown_version(self):
        cases=[[],[Pair(300,'EL_TYPED_V2'),Pair(2,'N')],
               [Pair(300,'EL_TYPED_V1'),Pair(40,'1.0')],
               [Pair(300,'EL_TYPED_V1'),Pair(2,'S'),Pair(1,'unfinished')],
               [Pair(300,'EL_TYPED_V1'),Pair(2,'L'),Pair(90,1)],
               [Pair(300,'EL_TYPED_V1'),Pair(2,'L'),Pair(2,'D'),Pair(90,1),Pair(2,'E')],
               [Pair(300,'EL_TYPED_V1'),Pair(3,'x trailing')],
               [Pair(300,'EL_TYPED_V1'),Pair(2,'N'),Pair(2,'N')]]
        for tokens in cases:
            with self.subTest(tokens=tokens), self.assertRaises(RuntimeError):
                self.h.call(Symbol('EL:STOREDECODE'),[tokens])
        entity=self.h.builtins['ENTMAKEX']([Pair(0,'XRECORD')]+cases[1])
        self.dictionary['EL_FIXED_V1']=entity
        before=copy.deepcopy((self.entities,self.dictionary))
        with self.assertRaises(RuntimeError): self.h.run('(EL:StoreRead)')
        self.assertEqual((self.entities,self.dictionary),before)

    def test_difference_reports_field_path_and_late_string_offset_without_long_values(self):
        left=[Pair(Symbol('NOTES'),'a'*1000+'原值')]
        right=[Pair(Symbol('NOTES'),'a'*1000+'变化')]
        diff=self.h.call(Symbol('EL:STOREDIFFERENCE'),[left,right,None])
        get=lambda key:self.h.call(Symbol('EL:GET'),[Symbol(key),diff])
        self.assertEqual(get('PATH'),[0,Symbol('NOTES')])
        self.assertEqual(get('STRING-OFFSET'),1000)
        self.assertLessEqual(len(get('EXPECTED')),80)
        self.assertIn('原值',get('EXPECTED'))
        self.assertIsNotNone(self.h.call(Symbol('EL:STOREDIFFERENCE'),[[1,2],[1],None]))
        self.assertIsNotNone(self.h.call(Symbol('EL:STOREDIFFERENCE'),[None,[1],None]))

    def test_typed_values_keep_empty_nil_boolean_integer_and_improper_lists(self):
        value=self.h.run("'((zero . 0) (real . 0.0) (true . T) (empty) (text . \"\") (tail a b . c))")
        # Generic native values retain the original wire contract; the public
        # V2 encoder handles business stores tested in StoreCompactTests.
        tokens=self.h.call(Symbol('EL:STOREENCODENATIVE'),[value,'EL_TYPED_V1'])
        self.assertEqual(self.h.call(Symbol('EL:STOREDECODE'),[tokens]),value)
        self.assertIn(Pair(90,0),tokens)
        self.assertIn(Pair(40,0.0),tokens)
        self.assertIn(Pair(2,'T'),tokens)

    def test_fallback_identity_persists_across_store_reload(self):
        self.h.builtins.update({'GETVAR': lambda key: {'CDATE': 20261009.12,
            'MILLISECS': 100}.get(key), 'EL:DRAWINGID': lambda: 'drawing.dwg'})
        identity = self.h.run("(EL:Get 'drawing-uuid (EL:StoreInitial))")
        self.assertTrue(identity.startswith('EL-'))
        self.h.run('(EL:StoreWrite (EL:StoreInitial))')
        self.h.run('(setq *EL:FallbackDrawingUUID* nil)')
        self.assertEqual(self.h.run("(EL:Get 'drawing-uuid (EL:StoreRead))"), identity)

    def test_foreign_or_copied_handle_is_not_owned(self):
        self.h.run("(setq store (EL:StoreInitial) record '((diagram-id . \"diagram1\")))")
        tag=[Pair(1000,x) for x in ('drawing-guid','diagram1','text','uid1','A')]
        self.entities['A']=[Pair(0,'TEXT'),Pair(5,'A'),[-3,['EL_FIXED_V1']+tag]]
        self.assertEqual(self.h.run('(EL:OwnedEntity "A" store record "text" "uid1")'),'A')
        self.entities['B']=[Pair(0,'TEXT'),Pair(5,'B'),[-3,['EL_FIXED_V1']+tag]]
        self.assertFalse(truth(self.h.run('(EL:OwnedEntity "B" store record "text" "uid1")')))
        self.assertFalse(truth(self.h.run('(EL:OwnedEntity "A" store record "text" "uid2")')))
        self.assertTrue(truth(self.h.run('(EL:ManagedEntity "B")')))
