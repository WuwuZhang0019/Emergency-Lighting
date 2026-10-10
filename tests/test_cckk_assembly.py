"""Standalone assembly adapter checks; no native CAD acceptance. Date: 2026-10-09."""
import pathlib
import unittest
from autolisp_host import Host, Pair, Symbol, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]

def field(data, key):
    for p in data or []:
        if isinstance(p, Pair) and p.car == key:
            return p.cdr
        if isinstance(p, list) and p[0] == key:
            return p[1:]

class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(ROOT / 'src/insert-circuit.lsp')
        self.vars = {'CMDECHO': 1, 'ATTREQ': 1, 'DRAGMODE': 0, 'CLAYER': 'old'}
        self.original = dict(self.vars)
        self.entities = {'old': [Pair(0, 'LINE')]}
        self.last = 'old'
        self.serial = 0
        self.states = {}
        self.allowed = ['普通', '预留']
        self.readonly = False
        self.ignore_write = False
        self.input = iter([1])
        self.h.frames[0].update({'PAUSE': 'pause', ':VLAX-TRUE': -1, ':VLAX-FALSE': 0})
        self.h.builtins.update({
            'TBLSEARCH': lambda kind, name: [Pair(2, name), Pair(70, 0), Pair(62, 7)],
            'GETVAR': lambda key: self.vars[key],
            'SETVAR': lambda key, value: self.vars.__setitem__(key, value),
            'INITGET': lambda *args: None, 'GETINT': lambda *args: next(self.input),
            'VL-LOAD-COM': lambda: None,
            'COMMAND': self.command, 'ENTMAKE': self.make,
            'ENTLAST': lambda: self.last, 'ENTGET': lambda e: self.entities.get(e),
            'ENTDEL': lambda e: self.entities.pop(e, None) and e,
            'TRANS': lambda point, *args: point,
            'VLAX-ENAME->VLA-OBJECT': lambda e: e,
            'VLA-GET-ISDYNAMICBLOCK': lambda e: -1,
            'VLAX-INVOKE': lambda e, method: [e],
            'VLA-GET-PROPERTYNAME': lambda e: '可见性1',
            'VLAX-GET-PROPERTY': lambda e, key: self.allowed,
            'VLA-GET-READONLY': lambda e: -1 if self.readonly else 0,
            'VLA-GET-VALUE': lambda e: self.states.get(e, '普通'),
            'VLAX-VARIANT-TYPE': lambda v: 8,
            'VLAX-MAKE-VARIANT': lambda v, typ: v,
            'VLA-PUT-VALUE': self.set_state,
        })

    def set_state(self, entity, value):
        if not self.ignore_write:
            self.states[entity] = value

    def make(self, data):
        self.serial += 1
        self.last = 'new' + str(self.serial)
        self.entities[self.last] = data
        return data

    def command(self, *args):
        self.assertEqual(args[0], '_.-INSERT')
        self.assertEqual(self.vars['CLAYER'], 'SYS_系统标注_E')
        point = [100., 200., 0.] if args[-1] == 'pause' else args[-1]
        if args[-1] != 'pause':
            self.assertEqual(args[-2], '_non')
        self.make([Pair(0, 'INSERT'), Pair(2, args[1]), Pair(8, self.vars['CLAYER']),
            Pair(10, point), Pair(41, 1.), Pair(42, 1.), Pair(50, 0.), Pair(210, [0., 0., 1.])])

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def test_one_through_eight_layout_visibility_labels_and_restore(self):
        for n in range(1, 9):
            with self.subTest(count=n):
                self.setUp()
                self.input = iter([n])
                self.h.run('(c:CCKK2)')
                reserve = 2 if n <= 6 else 1 if n == 7 else 0
                circuits = [(e,d) for e,d in self.entities.items() if field(d,2)=='fghjftyuk']
                self.assertEqual(len(circuits), n+reserve)
                for i,(e,d) in enumerate(circuits):
                    self.assertEqual(field(d,10), [6527., -5300.-1200.*i, 0.])
                    self.assertEqual(self.states[e], '普通' if i<n else '预留')
                    self.assertEqual(field(d,8), 'SYS_系统标注_E')
                texts = [d for d in self.entities.values() if field(d,0)=='TEXT']
                self.assertEqual(len(texts), 1+2*n+n+reserve)
                numbers = [d for d in texts if field(d,1).startswith('ZE')]
                self.assertEqual([field(d,1) for d in numbers], [f'ZE{i+1}' for i in range(n+reserve)])
                for i,d in enumerate(numbers):
                    self.assertEqual(field(d,11), [8627., -5160.-1200.*i, 0.])
                    self.assertEqual(field(d,7), '_TEL_DIM')
                    self.assertEqual(field(d,8), 'TEL_TEXT')
                    self.assertEqual(field(d,62), 256)
                self.assertEqual(sum(field(d,1)=='132W' for d in texts), n)
                self.assertEqual(sum(field(d,1)=='预留' for d in texts), 0)
                box = next(d for d in texts if field(d,1)=='CK-B1AL1')
                self.assertEqual(field(box,11), [2550., -255., 0.])
                self.assertEqual(field(box,7), 'ICDA-STYLE1')
                for d in texts:
                    self.assertEqual(field(d,72),1)
                    self.assertEqual(field(d,73),0)
                    self.assertEqual(field(d,40),350.)
                    self.assertEqual(field(d,41),.7)
                self.assertEqual(self.vars, self.original)
                self.assertEqual(self.entities['old'], [Pair(0,'LINE')])

    def test_invalid_count_reprompt_and_enter_defaults_to_one(self):
        self.assertIsNone(self.call('EL:CCKK2Rows', 0))
        self.assertIsNone(self.call('EL:CCKK2Rows', 9))
        self.assertIsNone(self.call('EL:CCKK2Rows', 1.5))
        self.input = iter([9, None])
        self.h.run('(c:CCKK2)')
        self.assertEqual(len(self.states),3)

    def test_unsupported_readonly_and_ignored_visibility_writes_fail(self):
        for failure in ('unsupported','readonly','ignored'):
            with self.subTest(failure=failure):
                self.setUp()
                if failure=='unsupported': self.allowed=['普通']
                if failure=='readonly': self.readonly=True
                if failure=='ignored': self.ignore_write=True
                with self.assertRaises(RuntimeError):
                    self.call('EL:CCKKVisibility','circuit','预留')

    def test_mid_assembly_failure_cleanup_preserves_old_entities(self):
        self.vars['CLAYER']='SYS_系统标注_E'
        self.h.frames[0]['*EL:CCKK2CREATED*']=None
        panel=self.call('EL:CCKK2Insert','dfgjhdrtyjtfgj4SADFG3',None)
        self.allowed=['普通']
        with self.assertRaises(RuntimeError):
            self.call('EL:CCKK2Build',panel,self.call('EL:CCKK2Rows',2))
        self.assertGreater(len(self.entities),1)
        self.assertTrue(truth(self.call('EL:CCKK2Cleanup')))
        self.assertEqual(self.entities,{'old':[Pair(0,'LINE')]})

    def test_original_commands_retain_texts_styles_and_colors(self):
        for cmd, count, expected, style, color in [
            ('CCKK',2,'132W','_TEL_DIM',256),('CCKK1',1,'CK-B1AL1','ICDA-STYLE1',0)]:
            self.setUp()
            self.h.run('(c:'+cmd+')')
            texts=[d for d in self.entities.values() if field(d,0)=='TEXT']
            self.assertEqual(len(texts),count)
            match=next(d for d in texts if field(d,1)==expected)
            self.assertEqual(field(match,7),style)
            self.assertEqual(field(match,62),color)
            self.assertEqual(self.vars,self.original)

if __name__ == '__main__':
    unittest.main()
