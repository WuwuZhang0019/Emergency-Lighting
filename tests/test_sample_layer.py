"""Layer sampling does not require a direct panel contact. Date: 2026-10-08."""
import unittest
from autolisp_host import Symbol, truth
import test_cad_adapter as adapter

class SampleLayerTests(unittest.TestCase):
    setUp = adapter.CadAdapterTests.setUp
    call = adapter.CadAdapterTests.call
    get = adapter.CadAdapterTests.get
    line = adapter.CadAdapterTests.line
    block = adapter.CadAdapterTests.block

    def prepare(self, attached=True, accept=False):
        self.h.load_definitions(adapter.ROOT/'src/main.lsp')
        self.block('BOX','P','2223',[0.,0.,0.])
        self.block('LAMP','D','lamp',[12.,0.,0.])
        if attached: self.line('2227',[1.,0.,0.],[5.,0.,0.],'W')
        self.line('2228',[5.,0.,0.],[11.,0.,0.],'W')
        self.selected=['2223','lamp','2228']+(['2227'] if attached else [])
        cfg=self.h.lookup('CFG');self.prompts=[];self.reviewed=[];self.saved=[];self.messages=[];self.scans=0
        params,body=self.h.functions[Symbol('EL:COLLECTENDPOINTSNAPSHOT')]
        original=[Symbol('LAMBDA'),params,*body]
        def collect(*args):
            self.scans+=1
            return self.h.call(original,list(args))
        def pick(prompt):
            self.prompts.append(prompt)
            self.assertLessEqual(len(self.prompts),2,'Must not force the same sample to be repicked')
            return ['2223' if len(self.prompts)==1 else '2228',[0.,0.,0.]]
        def review(rows):
            self.reviewed.append(rows)
            return [rows] if accept else None
        self.h.builtins.update({
            'EL:LOADCONFIG':lambda:cfg,'ENTSEL':pick,'EL:REVIEWEXITS':review,
            'EL:COLLECTENDPOINTSNAPSHOT':collect,'EL:SAVECONFIG':lambda c:self.saved.append(c) or c,
            'EL:REVIEWROLES':lambda s,c:c,'HANDENT':lambda h:h,'REDRAW':lambda *a:None,
            'PRINC':lambda *a:self.messages.extend(str(x) for x in a),'GRTEXT':lambda *a:None,
        })

    def test_downstream_sample_opens_actual_exits_and_cancel_does_not_rescan(self):
        self.prepare()
        self.h.run('(c:ELTRACE)')
        self.assertEqual([self.get('wire',s) for s in self.reviewed[0]],['2227'])
        self.assertEqual(len(self.prompts),2)
        self.assertEqual(self.scans,1)
        self.assertEqual(self.saved,[])
        self.assertIsNone(self.h.lookup('*EL:RESULT*'))
        self.assertIn('本次未生成统计结果',''.join(self.messages))

    def test_zero_exits_still_offers_review_for_layer_addition_or_cancel(self):
        self.prepare(attached=False)
        self.h.run('(c:ELTRACE)')
        self.assertEqual(len(self.reviewed),1)
        self.assertFalse(self.reviewed[0])
        self.assertEqual(self.scans,1)
        self.assertEqual(self.saved,[])
        self.assertIn('未发现接触箱体整体范围',''.join(self.messages))

    def test_downstream_sample_can_confirm_exit_and_reach_statistics(self):
        self.prepare(accept=True)
        self.h.run('(c:ELTRACE)')
        result=self.h.lookup('*EL:RESULT*')
        self.assertTrue(result)
        circuits=self.get('circuits',result)
        self.assertEqual(self.get('wire',self.get('seed',circuits[0])),'2227')
        self.assertIn('lamp',self.get('devices',circuits[0]))
        self.assertEqual(len(self.saved),1)
        self.assertEqual(len(self.prompts),2)
