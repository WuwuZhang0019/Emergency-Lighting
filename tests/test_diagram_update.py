"""Actual update functions against a finite DWG adapter. Date: 2026-10-09."""
import copy
import unittest
import test_diagram_store as db
import test_kernel as kernel
from autolisp_host import Pair, Symbol, truth

class UpdateTests(unittest.TestCase):
    generation_fixture=kernel.KernelTests.generation_fixture
    def setUp(self):
        db.StoreTests.setUp(self)
        for name in ('geometry','statistics','generation','fixed','panel','diagram-update','diagram-commands'):
            self.h.load_definitions(db.ROOT/'src'/f'{name}.lsp')
        self.generation_fixture()
        self.h.run('''(setq template (EL:Put 'panel (EL:Put 'name "dfgjhdrtyjtfgj4SADFG3" (EL:Get 'panel template))
          (EL:Put 'circuit (EL:Put 'name "fghjftyuk" (EL:Get 'circuit template)) template)))
          (setq store (EL:StoreInitial) result (EL:Put 'panel "source" result))
          (setq cs (EL:Get 'circuits result))
          (setq cs (list (EL:Put 'seed-key 's1 (EL:Put 'output-order 1 (EL:Put 'circuit-uid "u1" (car cs))))
            (EL:Put 'seed-key 's2 (EL:Put 'output-order 2 (EL:Put 'circuit-uid "u2" (cadr cs))))))
          (setq result (EL:Put 'circuits cs result))
          (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))
          (setq record '((diagram-id . "d1") (source-panel-handle . "source") (panel-output-handle . "panel")))''')
        self.writes=[]; self.dynamic={}; self.deleted=[]; self.counter=0
        def text_write(e,value):
            self.writes.append((e,value))
            self.entities[e]=[Pair(1,value) if isinstance(p,Pair) and p.car==1 else p for p in self.entities[e]]
        def move(e,start,end):
            self.entities[e]=[Pair(10,end) if isinstance(p,Pair) and p.car==10 else p for p in self.entities[e]]
        def create_text(space,row,plan,layer):
            self.counter+=1; e='new-text-'+str(self.counter)
            self.entity(e,'TEXT',self.get('text-position',row),self.get('text',row)); return e
        def create_block(space,name,pos,scale,rotation,prop,value,layer):
            self.counter+=1; e='new-block-'+str(self.counter); self.entity(e,'INSERT',pos)
            self.dynamic[e]=value; return e
        self.h.builtins.update({'VLAX-GET-ACAD-OBJECT':lambda:'app','VLA-GET-ACTIVEDOCUMENT':lambda _:'doc',
          'VLA-GET-MODELSPACE':lambda _:'space','VLAX-ENAME->VLA-OBJECT':lambda e:e,
          'VLAX-VLA-OBJECT->ENAME':lambda e:e,'VLAX-3D-POINT':lambda p:p,
          'EL:DYNAMICPROPERTY':lambda e,name:e,'VLA-GET-VALUE':lambda e:self.dynamic.get(e),
          'VLAX-VARIANT-VALUE':lambda v:v,'EL:SETDYNAMICVALUE':lambda e,name,value:self.dynamic.__setitem__(e,value) or True,
          'VLA-PUT-TEXTSTRING':text_write,'VLA-MOVE':move,'EL:CREATEANNOTATION':create_text,'EL:CREATEBLOCK':create_block,
          'REGAPP':lambda _:True,'ENTDEL':lambda e:self.entities.pop(e,None) and self.deleted.append(e) or e})
        self.entity('panel','INSERT',[0.,0.,0.]); self.dynamic['panel']='CAP300'
        handles=[]
        for i,row in enumerate(self.get('rows',self.h.lookup('PLAN'))):
            key=self.get('circuit-uid',row); block=f'b{i}'; text=f't{i}'
            self.entity(block,'INSERT',self.get('position',row));self.dynamic[block]=self.get('value',row)
            self.call('EL:TagEntity',block,self.h.lookup('STORE'),self.h.lookup('RECORD'),'circuit',key)
            h=[Pair(Symbol('CIRCUIT-UID'),key),Pair(Symbol('BLOCK-HANDLE'),block)]
            if self.get('text',row):
                self.entity(text,'TEXT',self.get('text-position',row),self.get('text',row))
                self.call('EL:TagEntity',text,self.h.lookup('STORE'),self.h.lookup('RECORD'),'text',key)
                h.append(Pair(Symbol('TEXT-HANDLE'),text))
            handles.append(h)
        self.h.frames[0]['HANDLES']=handles
        self.h.run("(setq record (EL:Put 'rows (EL:RecordRows result plan handles) (EL:Put 'plan plan record)))")
        self.call('EL:TagEntity','panel',self.h.lookup('STORE'),self.h.lookup('RECORD'),'panel','panel')

    def call(self,fn,*args): return self.h.call(Symbol(fn.upper()),list(args))
    def get(self,key,row): return self.call('EL:Get',Symbol(key.upper()),row)
    def entity(self,e,kind,point,text=''):
        self.entities[e]=[Pair(-1,e),Pair(5,e),Pair(0,kind),Pair(10,point),Pair(1,text),Pair(8,'EL-SYSTEM'),
          Pair(410,'Model'),Pair(41,1.),Pair(42,1.),Pair(43,1.),Pair(50,0.)]
    def update(self,structural=False):
        return self.h.run("(EL:ApplyUpdate result template plan record store "+('T' if structural else 'nil')+")")

    def test_power_update_keeps_handles_manual_position_and_no_reserve_text(self):
        self.entities['t0']=[Pair(10,[99.,88.,0.]) if isinstance(p,Pair) and p.car==10 else p for p in self.entities['t0']]
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'watts 135 (car cs)) (cdr cs)) result)) (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
        updated=self.update(); self.assertEqual(self.writes,[('t0','135W')]); self.assertEqual(self.counter,0)
        self.assertEqual(next(p.cdr for p in self.entities['t0'] if isinstance(p,Pair) and p.car==10),[99.,88.,0.])
        self.assertEqual([self.get('block-handle',r) for r in self.get('rows',updated)],['b0','b1','b2','b3'])
        self.assertEqual(len([e for e in self.entities if e.startswith('t')]),2)

    def test_missing_text_only_is_recreated(self):
        del self.entities['t0']; updated=self.update()
        self.assertEqual(self.counter,1);self.assertEqual(self.get('text-handle',self.get('rows',updated)[0]),'new-text-1')
        self.assertEqual(len([r for r in self.get('rows',updated) if self.get('text-handle',r)]),2)

    def test_remove_retains_reserve_identity_and_cleans_owned_row(self):
        self.h.run("(setq result (EL:Put 'circuits (cdr cs) result)) (setq plan (EL:FixedPlan result template 'cap600 '(0.0 0.0 0.0) 0.0 1.0))")
        updated=self.update(True)
        self.assertEqual(self.deleted,['b0','t0']);self.assertEqual(self.counter,0)
        self.assertEqual([self.get('block-handle',r) for r in self.get('rows',updated)],['b1','b2','b3'])
        self.assertEqual(self.dynamic['panel'],'CAP600')

    def test_ground_change_updates_state_and_not_power(self):
        self.h.run("(setq result (EL:Put 'circuits (cons (EL:Put 'is-ground T (car cs)) (cdr cs)) result)) (setq plan (EL:FixedPlan result template 'cap300 '(0.0 0.0 0.0) 0.0 1.0))")
        self.update();self.assertEqual(self.dynamic['b0'],'GROUND'); self.assertEqual(self.writes,[])
