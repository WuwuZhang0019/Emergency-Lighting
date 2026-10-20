"""Explicit circuit start selection and search boundaries. Date: 2026-10-20.

Finite CAD adapters only; original DWG acceptance remains pending.
"""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_fixed_diagnostics as diag


class CircuitStartTests(unittest.TestCase):
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get
    line = diag.FixedDiagnosticTests.line
    block = diag.FixedDiagnosticTests.block
    plan = diag.FixedDiagnosticTests.plan
    logging = diag.FixedDiagnosticTests.logging

    def setUp(self):
        diag.FixedDiagnosticTests.setUp(self)
        self.arrows, self.opened, self.returned = [], [], []
        self.h.builtins.update({
            'EL:DRAWTRANSIENT': lambda *a: self.arrows.append(a),
            'EL:HIGHLIGHTPICK': lambda *a: None,
            'EL:EDITPANEL': lambda r,c: self.opened.append((r,c)),
            'EL:PANELSTARTDIALOG': lambda: self.returned.append(True),
            'ALERT': lambda *a: None,
        })

    def starts(self, *specs):
        rows = []
        for handle, side in specs:
            wire = self.call('EL:WireRecord', handle, self.cfg)
            ep = self.call('EL:By', Symbol('KEY'), [handle, Symbol(side.upper())], self.get('ends', wire))
            row = self.call('EL:Put',Symbol('WIRE'),handle,None)
            row = self.call('EL:Put',Symbol('END'),Symbol(side.upper()),row)
            rows.append(self.call('EL:Put',Symbol('POINT'),self.get('point',ep),row))
        self.cfg = self.call('EL:Put', Symbol('CIRCUIT-STARTS'), rows, self.cfg)
        self.cfg = self.call('EL:Put', Symbol('AUTO-PANEL'), 'panel', self.cfg)
        return rows

    def recognize(self):
        return self.call('EL:RecognizeFixed', self.cfg, 'panel')

    def devices(self, result):
        return sorted(sorted(self.get('devices', c) or []) for c in self.get('circuits', result))

    def trunk(self):
        self.line('trunk', [10.,-20.,0.], [10.,20.,0.], 'W')
        self.selected = ['panel','trunk']  # Deliberately no feeder.
        for i,y in enumerate((-12.,-6.,0.,6.,12.)):
            self.line(f'w{i}', [10.,y,0.], [29.,y,0.], 'W')
            self.block('LAMP','D',f'd{i}',[30.,y,0.])
            self.selected += [f'w{i}', f'd{i}']

    def test_direct_panel_selected_roots_only_and_downstream_t_branch(self):
        self.line('other',[0.,1.,0.],[0.,9.,0.],'W')
        self.block('LAMP','D','other-device',[0.,10.,0.])
        self.selected += ['other','other-device']
        self.starts(('w1','start'))
        self.assertEqual(self.devices(self.recognize()), [['a','b']])

    def test_trunk_without_feeder_yields_five_independent_circuits(self):
        self.trunk()
        self.starts(*[(f'w{i}','start') for i in range(5)])
        result = self.recognize()
        self.assertEqual(self.devices(result), [[f'd{i}'] for i in range(5)])
        for c in self.get('circuits',result): self.assertNotIn('trunk',self.get('wires',c))
        self.assertTrue(truth(self.call('EL:FreshResult',result,self.cfg)))
        self.line('trunk',[10.,-21.,0.],[10.,21.,0.],'W')
        self.assertFalse(truth(self.call('EL:FreshResult',result,self.cfg)))

    def test_only_picked_trunk_outlets_are_counted(self):
        self.trunk(); self.starts(('w0','start'),('w4','start'))
        self.assertEqual(self.devices(self.recognize()), [['d0'],['d4']])

    def test_reverse_drawing_order_uses_picked_end_for_number_scope(self):
        self.trunk(); self.line('w0',[29.,-12.,0.],[10.,-12.,0.],'W')
        self.starts(('w0','end'))
        result = self.recognize()
        self.assertEqual(self.devices(result), [['d0']])
        scope = self.get('number-scope',self.get('circuits',result)[0])
        self.assertFalse(self.get('issues',scope))
        wire = self.call('EL:By',Symbol('ID'),'w0',self.get('wires',self.get('snapshot',result)))
        self.assertEqual(self.call('EL:NumberRootStation',wire,self.get('snapshot',result),self.cfg,None),[19.])

    def test_coincident_roots_do_not_join_each_other(self):
        self.line('s1',[10.,0.,0.],[19.,10.,0.],'W')
        self.line('s2',[10.,0.,0.],[19.,-10.,0.],'W')
        self.block('LAMP','D','d1',[20.,10.,0.]); self.block('LAMP','D','d2',[20.,-10.,0.])
        self.selected = ['panel','s1','s2','d1','d2']
        self.starts(('s1','start'),('s2','start'))
        self.assertEqual(self.devices(self.recognize()), [['d1'],['d2']])

    def test_source_gap_never_backtracks_but_device_side_gap_continues(self):
        self.line('root',[10.,0.,0.],[20.,0.,0.],'W')
        self.line('upstream',[0.,0.,0.],[8.,0.,0.],'W')
        self.line('downstream',[22.,0.,0.],[29.,0.,0.],'W')
        self.block('LAMP','D','up-device',[0.,0.,0.]); self.block('LAMP','D','down-device',[30.,0.,0.])
        self.selected = ['panel','root','upstream','downstream','up-device','down-device']
        self.starts(('root','start'))
        self.assertEqual(self.devices(self.recognize()), [['down-device']])

    def test_shared_downstream_still_blocks_generation(self):
        self.trunk(); self.line('join',[20.,-12.,0.],[20.,-6.,0.],'W'); self.selected.append('join')
        self.starts(('w0','start'),('w1','start'))
        result = self.call('EL:PanelCompute',self.recognize(),self.h.run("'((\"LAMP\" . 5))"),self.cfg)
        self.assertFalse(truth(self.get('can-generate',result)))

    def test_missing_or_moved_start_must_be_repicked(self):
        self.starts(('w1','start'))
        self.line('w1',[2.,0.,0.],[9.,0.,0.],'W')
        with self.assertRaises(RuntimeError): self.recognize()

    def test_config_rules_and_native_store_roundtrip(self):
        import test_diagram_store as db
        self.starts(('w1','start'))
        self.assertTrue(truth(self.call('EL:ConfigValid',self.cfg,'adapter-fixture.dwg')))
        before = self.call('EL:RecognitionRules',self.cfg)
        self.starts(('w1','end'))
        self.assertNotEqual(before,self.call('EL:RecognitionRules',self.cfg))
        f = db.StoreTests(); f.setUp()
        self.addCleanup(f.doCleanups)
        f.h.frames[0]['STARTCFG'] = self.cfg
        f.h.run("(setq store (EL:Put 'diagrams (list (list '(source-panel-handle . \"panel\") (cons 'config startcfg))) (EL:StoreInitial)))")
        self.assertTrue(truth(f.h.run('(EL:StoreWrite store)')))
        self.assertTrue(truth(f.h.run('(equal store (EL:StoreRead))')))

    def picks(self, values):
        sequence = iter(values)
        self.h.builtins['EL:PICKMODEL'] = lambda *a: next(sequence)

    def native_picks(self, values):
        self.h.builtins.pop('EL:PICKMODEL', None)
        sequence = iter(values)
        error = [7]  # A stale native error must not turn Enter into another miss.
        previous = self.h.builtins['GETVAR']
        self.h.builtins['GETVAR'] = lambda key: error[0] if key == 'ERRNO' else previous(key)
        self.h.builtins['SETVAR'] = lambda key, value: error.__setitem__(0, value)
        def select(prompt):
            value = next(sequence)
            if value == 'miss':
                error[0] = 7
                return None
            if value == 'escape':
                raise RuntimeError('Function cancelled')
            return value
        self.h.builtins['ENTSEL'] = select

    def test_blank_click_between_wire_picks_does_not_finish_selection(self):
        self.native_picks([['w1', [1., 0., 0.]], 'miss', 'miss',
                           ['w1', [9., 0., 0.]], None])
        cfg = self.call('EL:PickCircuitStarts', self.cfg)
        rows = self.get('circuit-starts', cfg)
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.get('end', rows[0]), Symbol('END'))
        self.assertEqual(self.opened, [])

    def test_enter_after_miss_finishes_with_existing_selection(self):
        self.native_picks([['w1', [1., 0., 0.]], 'miss', None])
        cfg = self.call('EL:PickCircuitStarts', self.cfg)
        self.assertEqual(len(self.get('circuit-starts', cfg)), 1)
        self.native_picks([None])
        self.assertIsNone(self.call('EL:PickCircuitStarts', self.cfg))

    def test_escape_after_miss_never_starts_recognition(self):
        self.call('EL:RememberStartPanel', 'panel', '箱三')
        self.native_picks([['w1', [1., 0., 0.]], 'miss', 'escape'])
        self.call('EL:FixedStartPick')
        self.assertEqual(self.opened, [])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.get('number', self.call('EL:StartPickContext')), '箱三')

    def test_actual_panel_number_then_continuous_starts_reaches_editor(self):
        self.trunk()
        self.entities['number'] = [Pair(0,'TEXT'),Pair(1,'箱一')]
        self.h.builtins['NENTSEL'] = lambda *a: ['number',[0.,0.,0.]]
        self.picks([['panel',[0.,0.,0.]],['w0',[10.2,-12.,0.]],['w4',[10.2,12.,0.]],None])
        self.call('EL:FixedStatPick')
        self.assertEqual(len(self.opened),1)
        result,cfg = self.opened[0]
        self.assertEqual(self.get('panel-number',result),'箱一')
        self.assertEqual(self.devices(result),[['d0'],['d4']])
        self.assertEqual(len(self.get('circuit-starts',cfg)),2)
        self.assertGreater(len(self.arrows),0)

    def test_old_target_is_not_rebound_after_second_pick(self):
        record = [Pair(Symbol('DIAGRAM-ID'),'old-diagram'), Pair(Symbol('SOURCE-PANEL-HANDLE'),'old-source')]
        self.h.builtins['EL:REPICKRECORD'] = lambda *a: record
        self.h.builtins['EL:STORERECORD'] = lambda diagram_id: record if diagram_id == 'old-diagram' else None
        self.picks([['panel',[0.,0.,0.]],None])
        self.call('EL:FixedStatPick')
        self.call('EL:RememberStartPanel','panel','箱一')
        self.picks([['w1',[1.,0.,0.]],None])
        self.call('EL:FixedStartPick')
        result = self.opened[0][0]
        self.assertIsNone(self.get('update-diagram-id',result))
        self.assertIsNone(self.get('update-source-panel',result))
        self.assertEqual(self.writes,[])

    def test_duplicate_pick_changes_direction_without_adding_circuit(self):
        self.picks([['w1',[1.,0.,0.]],['w1',[9.,0.,0.]],None])
        cfg = self.call('EL:PickCircuitStarts',self.cfg)
        rows = self.get('circuit-starts',cfg)
        self.assertEqual(len(rows),1)
        self.assertEqual(self.get('end',rows[0]),Symbol('END'))

    def test_midpoint_asks_direction_and_transforms_ucs(self):
        self.picks([['w1',[-95.,0.,0.]],None])
        asked=[]
        self.h.builtins['TRANS'] = lambda p,a,b: [p[0]+100.,p[1],p[2]]
        self.h.builtins['GETPOINT'] = lambda p: asked.append(p) or [-99.,0.,0.]
        cfg = self.call('EL:PickCircuitStarts',self.cfg)
        self.assertEqual(len(asked),1)
        self.assertEqual(self.get('end',self.get('circuit-starts',cfg)[0]),Symbol('START'))

    def test_cancel_then_second_button_reuses_panel_and_number(self):
        self.entities['number']=[Pair(0,'TEXT'),Pair(1,'箱二')]
        self.h.builtins['NENTSEL']=lambda *a:['number']
        self.picks([['panel',[0.,0.,0.]],None])
        self.call('EL:FixedStatPick')
        self.assertEqual(self.returned,[])
        self.assertEqual(self.get('number',self.call('EL:StartPickContext')),'箱二')
        self.h.builtins['NENTSEL']=lambda *a:self.fail('number was requested again')
        self.picks([['w1',[1.,0.,0.]],None])
        self.call('EL:FixedStartPick')
        self.assertEqual(self.get('panel-number',self.opened[0][0]),'箱二')

    def test_escape_preserves_context_and_does_not_write(self):
        self.call('EL:RememberStartPanel','panel','箱三')
        def abort(*a): raise RuntimeError('Function cancelled')
        self.h.builtins['EL:PICKMODEL']=abort
        self.call('EL:FixedStartPick')
        self.assertEqual(self.get('number',self.call('EL:StartPickContext')),'箱三')
        self.assertEqual(self.writes,[])
        self.assertEqual(self.returned,[])

    def test_context_does_not_cross_drawings(self):
        self.call('EL:RememberStartPanel','panel','箱四')
        self.h.builtins['NAMEDOBJDICT']=lambda:'OTHER-NOD'
        self.assertIsNone(self.call('EL:StartPickContext'))

    def test_polyline_and_multiple_styles_can_be_picked_together(self):
        self.trunk()
        self.entities['w0']=[Pair(0,'LWPOLYLINE'),Pair(5,'w0'),Pair(8,'W'),Pair(70,0),
            Pair(38,0.),Pair(210,[0.,0.,1.]),Pair(410,'Model'),Pair(10,[10.,-12.]),
            Pair(10,[20.,-12.]),Pair(10,[29.,-12.])]
        self.entities['w4'].append(Pair(6,'DASHED'))
        self.picks([['w0',[10.,-12.,0.]],['w4',[10.,12.,0.]],None])
        self.cfg=self.call('EL:PickCircuitStarts',self.cfg)
        self.assertEqual(len(self.get('wire-styles',self.cfg)),2)
        self.assertEqual(self.devices(self.recognize()),[['d0'],['d4']])

    def test_second_button_without_panel_does_not_pick_wires(self):
        self.h.builtins['EL:PICKMODEL']=lambda *a:self.fail('wire picked before panel')
        self.call('EL:FixedStartPick')
        self.assertEqual(self.returned,[])
        self.assertEqual(self.writes,[])

    def test_reselect_adds_circuit_and_preserves_manual_inputs_and_uids(self):
        self.trunk(); self.starts(('w0','start'))
        record=self.call('EL:NewRecord','panel',self.call('EL:StoreInitial'))
        old=self.call('EL:PreparedResult',self.recognize(),record)
        self.h.frames[0]['OLD']=old
        self.h.run('''(setq *EL:StartPickResume* (list (cons 'result
            (EL:Put 'device-overrides '(("LAMP" (watts-set . T) (watts . 7))) old))
          '(powers ("LAMP" . 7)) '(capacity . cap600) '(position (page . 0))))''')
        self.starts(('w0','start'),('w4','start'))
        result=self.call('EL:StartPickResumeResult',self.recognize(),self.cfg)
        rows=self.get('circuits',result)
        self.assertEqual(len(rows),2)
        self.assertEqual(self.get('circuit-uid',rows[0]),self.get('circuit-uid',self.get('circuits',old)[0]))
        self.assertTrue(self.get('circuit-uid',rows[1]))
        self.assertTrue(self.get('device-overrides',result))
        resume=self.h.lookup('*EL:DLRESUME*')
        self.assertEqual(self.get('capacity',resume),Symbol('CAP600'))
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',resume)),7)
        self.assertEqual(self.get('config',resume),self.cfg)

    def test_cancel_from_existing_panel_keeps_draft_page_and_values(self):
        self.starts(('w1','start')); result=self.recognize()
        self.call('EL:RememberStartPanel','panel','保留箱号')
        self.h.frames[0]['DRAFT']=result
        self.h.frames[0]['NEWCFG']=self.cfg
        self.h.run('''(setq *EL:StartPickResume* (list (cons 'result draft) (cons 'config newcfg)
          '(powers ("LAMP" . 9)) '(capacity . cap600) '(position (page . 8))))''')
        self.picks([None]); self.call('EL:FixedStartPick')
        self.assertEqual(self.opened[0][0],result)
        resume=self.h.lookup('*EL:DLRESUME*')
        self.assertEqual(self.get('page',self.get('position',resume)),8)
        self.assertEqual(self.call('EL:Get','LAMP',self.get('powers',resume)),9)
        self.assertEqual(self.writes,[])


if __name__ == '__main__':
    unittest.main()
