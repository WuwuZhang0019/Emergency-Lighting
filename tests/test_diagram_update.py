"""Finite CAD generation fixture. Date: 2026-10-14. Status: current."""
import copy
import math
import unittest
import test_diagram_store as db
import test_kernel as kernel
from autolisp_host import Pair, Symbol, truth
from test_cckk_assembly import field

class UpdateTests(unittest.TestCase):
    generation_fixture=kernel.KernelTests.generation_fixture
    def setUp(self):
        db.StoreTests.setUp(self)
        for name in ('geometry','statistics','generation','fixed','panel','diagram-update','diagram-commands','insert-circuit'):
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
            updated=[]
            for p in self.entities[e]:
                code=p.car if isinstance(p,Pair) else p[0]
                if code in (10,11):
                    point=p.cdr if isinstance(p,Pair) else p[1:]
                    p=Pair(code,[point[i]+end[i]-start[i] for i in range(3)])
                updated.append(p)
            self.entities[e]=updated
        def create_text(space,row,plan,layer):
            self.counter+=1; e='new-text-'+str(self.counter)
            self.entity(e,'TEXT',self.get('text-position',row),self.get('text',row)); return e
        def create_block(space,name,pos,scale,rotation,prop,value,layer):
            self.counter+=1; e='new-block-'+str(self.counter); self.entity(e,'INSERT',pos)
            self.dynamic[e]=value; return e
        self.last=None
        def make_text(data):
            self.counter+=1; self.last='new-text-'+str(self.counter)
            self.entities[self.last]=[Pair(-1,self.last),Pair(5,self.last),Pair(410,'Model')]+data
            return data
        self.h.builtins.update({'ENTMAKE':make_text,'ENTLAST':lambda:self.last,'TBLSEARCH':lambda *args:[Pair(70,0),Pair(62,7)],'VLAX-GET-ACAD-OBJECT':lambda:'app','VLA-GET-ACTIVEDOCUMENT':lambda _:'doc',
          'VLA-GET-MODELSPACE':lambda _:'space','VLAX-ENAME->VLA-OBJECT':lambda e:e,
          'VLAX-VLA-OBJECT->ENAME':lambda e:e,'VLAX-3D-POINT':lambda p:p,
          'EL:DYNAMICPROPERTY':lambda e,name:e,'VLA-GET-VALUE':lambda e:self.dynamic.get(e),
          'VLAX-VARIANT-VALUE':lambda v:v,'EL:SETDYNAMICVALUE':lambda e,name,value:self.dynamic.__setitem__(e,value) or True,
          'VLA-PUT-TEXTSTRING':text_write,'VLA-MOVE':move,'EL:CREATEANNOTATION':create_text,'EL:CREATEBLOCK':create_block,
          'VLA-PUT-LAYER':lambda *args:None,'VLA-PUT-COLOR':lambda *args:None,'REGAPP':lambda _:True,'ENTDEL':lambda e:self.entities.pop(e,None) and self.deleted.append(e) or e})
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
        labels=[]
        for label in self.call('EL:CCKKLabels',self.h.lookup('PLAN')):
            uid=self.get('uid',label); entity='caption-'+uid
            parent='panel' if uid=='panel-label' else next(self.get('block-handle',r) for r in self.get('rows',self.h.lookup('RECORD')) if self.get('circuit-uid',r)==self.get('parent-uid',label))
            spec=self.call('EL:CCKKCaptionDef',self.get('kind',label))
            made=self.call('EL:CCKKText',parent,self.get('text',label),*spec[1:])
            self.entities[entity]=[Pair(p.car,entity) if isinstance(p,Pair) and p.car in (-1,5) else p
                                   for p in self.entities.pop(made)]
            self.call('EL:TagEntity',entity,self.h.lookup('STORE'),self.h.lookup('RECORD'),'text',uid)
            label=self.call('EL:Put',Symbol('CCKK-TEXT-VERSION'),1,label)
            labels.append(self.call('EL:Put',Symbol('HANDLE'),entity,label))
        self.counter=0
        self.h.frames[0]['LABELS']=labels
        self.h.run("(setq record (EL:Put 'cckk-labels labels record))")

    def call(self,fn,*args): return self.h.call(Symbol(fn.upper()),list(args))
    def get(self,key,row): return self.call('EL:Get',Symbol(key.upper()),row)
    def entity(self,e,kind,point,text=''):
        self.entities[e]=[Pair(-1,e),Pair(5,e),Pair(0,kind),Pair(10,point),Pair(1,text),Pair(8,'EL-SYSTEM'),
          Pair(410,'Model'),Pair(41,1.),Pair(42,1.),Pair(43,1.),Pair(50,0.)]










    def install_transaction(self):
        self.undo=[]
        def begin(_): self.undo.append(copy.deepcopy((self.entities,self.dictionary,self.dynamic)))
        def rollback(*args):
            self.assertEqual(args,('_.UNDO','1'))
            self.entities,self.dictionary,self.dynamic=copy.deepcopy(self.undo.pop())
        def remove(_,key): return self.dictionary.pop(key,None)
        self.h.builtins.update({'VLA-STARTUNDOMARK':begin,'VLA-ENDUNDOMARK':lambda _:None,
          'COMMAND-S':rollback,'REDRAW':lambda:None,'DICTREMOVE':remove,
          'GETVAR':lambda key:1 if key=='UNDOCTL' else 'drawing-guid',
          'EXIT':lambda:(_ for _ in ()).throw(RuntimeError('LISP exit'))})






    def install_sync(self):
        self.install_transaction()
        self.h.frames[0][':VLAX-FALSE']=0
        self.h.builtins.update({'TBLSEARCH':lambda *args:[Pair(70,0),Pair(62,7)],
          'EL:EFFECTIVENAME':lambda e:'dfgjhdrtyjtfgj4SADFG3' if e=='panel' else 'fghjftyuk',
          'VLA-GET-READONLY':lambda e:0,
          'EL:ALLOWEDVALUES':lambda e:['CAP300','CAP600','CAP1000'] if e=='panel' else ['NORMAL','GROUND','RESERVE'],
          'EL:TEMPLATERUNTIMEVALID':lambda *args:True,'EL:FRESHRESULT':lambda *args:True,
          'EL:UNIQUEDIAGRAM':lambda *args:True,'EL:WRITEDATA':lambda *args:True})
        self.h.run('''(setq cs (mapcar '(lambda (c) (EL:Put 'seed (list (cons 'key (EL:Get 'seed-key c))) c)) cs))
          (setq result (EL:Put 'circuits cs result) *EL:Root* "root/")
          (setq record (EL:Put 'template template (EL:Put 'status 'current (EL:Put 'capacity-option 'cap300
            (EL:Put 'power-signature (EL:Signature (EL:Get 'power-config result)) record)))))
          (EL:StoreWrite (EL:StorePutDiagram record store))''')
