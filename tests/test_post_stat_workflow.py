"""Post-statistics setup and explicit selection gates. Date: 2026-10-13.

Runs actual command/dialog functions with finite CAD/DCL adapters.
"""
import unittest
import tempfile
from pathlib import Path
import test_device_library as library_backend
import test_fixed_diagnostics as diag
import test_diagram_store as db
from autolisp_host import Pair, Symbol, truth


class PostStatWorkflowTests(unittest.TestCase):
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get
    line = diag.FixedDiagnosticTests.line
    block = diag.FixedDiagnosticTests.block
    plan = diag.FixedDiagnosticTests.plan
    logging = diag.FixedDiagnosticTests.logging

    def setUp(self):
        diag.FixedDiagnosticTests.setUp(self)
        self.capture_calls, self.actions = [], []
        self.closed = None
        self.h.builtins.update({'GET_TILE': lambda key: self.tiles.get(key, ''),
                               'DONE_DIALOG': self.done,
                               'START_DIALOG': self.start})
        self.result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        record = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        self.result = self.call('EL:PreparedResult', self.result, record)
        self.powers = self.h.run("'((\"LAMP\" . 5))")
        # Generation workflow fixture has a registered non-ground lamp.
        # Empty/unknown-library generation is covered separately in device recognition checks.
        catalog=self.call('EL:DLCatalogInitial','LIB-WORKFLOW')
        entry=self.call('EL:DLEntryNew',catalog,'LAMP')
        values={'display':'Lamp','watts':5,'ground-confirmed':True,'active':True,'status':Symbol('READY'),
                'asset-revision':1,'block-file':'assets/ELDEV1/1/block.dwg',
                'legend-file':'assets/ELDEV1/1/legend.sld','legend-size':[800,600],'legend-checksum':'sld-123-31'}
        for key,value in values.items():entry=self.call('EL:Put',Symbol(key.upper()),value,entry)
        catalog=self.call('EL:DLUpsert',catalog,entry)
        snapshot=self.h.run("'((root . \"library-fixture/\") (present))")
        snapshot=self.call('EL:Put',Symbol('CATALOG'),catalog,self.call('EL:Put',Symbol('INDEX'),self.call('EL:DLIndex',catalog),snapshot))
        self.h.builtins['EL:DLSNAPSHOT']=lambda:snapshot
        self.h.builtins['EL:DLREMEMBERINPUTS']=lambda *args:True

    def done(self, status):
        self.closed = status

    def start(self):
        self.closed = None
        self.actions.pop(0)()
        self.assertIsNotNone(self.closed, 'test action must close the dialog')
        return self.closed

    def confirm(self):
        self.call('EL:PanelCapacity', 'p_600')

    def dialog(self):
        return self.call('EL:PanelDialog', self.result, self.cfg, self.powers, None)

    def test_inline_legend_selection_preserves_box_values_and_navigation(self):
        snapshot=self.h.builtins['EL:DLSNAPSHOT']()
        self.h.set('*EL:DLSESSIONSNAPSHOT*',snapshot)
        callbacks={}
        self.h.builtins['ACTION_TILE']=lambda k,v:callbacks.__setitem__(k,v)
        self.h.builtins['EL:DLLegend'.upper()]=lambda *args:None
        def action():
            self.tiles['b_watts0']='7'
            self.h.run(callbacks['f_image0'])
            self.assertIsNone(self.closed)
            self.assertEqual(self.tiles['dl_block'],'LAMP')
            self.assertEqual(self.tiles['dl_watts'],'5')
            self.assertEqual(self.tiles['b_watts0'],'7')
            self.tiles['dl_display']='库名称输入'
            self.h.run(callbacks['b_library'])
            self.assertEqual(self.closed,11)
            self.assertEqual(self.get('display',self.call('EL:DLUIEntry')),'库名称输入')
        self.actions=[action]
        result=self.dialog()
        self.assertTrue(self.get('library-panel',result))
        self.assertEqual(self.writes,[])

    def test_inline_saved_default_refresh_preserves_manual_box_watts(self):
        snapshot=self.h.builtins['EL:DLSNAPSHOT']()
        self.h.set('*EL:DLSESSIONSNAPSHOT*',snapshot)
        prepared=self.call('EL:DLPrepare',self.result,self.powers,snapshot,None)
        self.result=self.get('result',prepared); self.powers=self.get('powers',prepared)
        callbacks={}
        self.h.builtins['ACTION_TILE']=lambda k,v:callbacks.__setitem__(k,v)
        self.h.builtins['EL:DLLegend'.upper()]=lambda *args:None
        def saved():
            catalog=self.get('catalog',snapshot)
            entry=self.get('devices',catalog)[0]
            entry=self.call('EL:Put',Symbol('WATTS'),9,entry)
            catalog=self.call('EL:DLUpsert',catalog,entry)
            current=self.call('EL:Put',Symbol('CATALOG'),catalog,snapshot)
            current=self.call('EL:Put',Symbol('INDEX'),self.call('EL:DLIndex',catalog),current)
            self.h.set('*EL:DLUISTATE*',self.call('EL:Put',Symbol('SNAPSHOT'),current,self.h.lookup('*EL:DLUISTATE*')))
        self.h.builtins['EL:DLUISAVEWORK']=saved
        def action():
            self.tiles['b_watts0']='7'
            self.h.run(callbacks['f_image0'])
            self.h.run(callbacks['dl_save'])
            self.assertEqual(self.tiles['b_watts0'],'7')
            draft=self.h.lookup('*EL:PANELDRAFT*')
            self.assertEqual(self.get('watts',self.call('EL:DLOverride','LAMP',draft)),7)
            self.assertEqual(self.get('watts',self.get('entry',self.call('EL:DLReference','LAMP',draft))),9)
            self.done(0)
        self.actions=[action]
        self.dialog()

    def test_statistics_without_template_open_panel_without_setup_or_publication(self):
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: self.fail('setup before generation')
        self.h.builtins['EL:PUBLISHDIAGRAM'] = lambda *args: self.fail('must not publish before review')
        self.actions = [lambda: self.done(0)]
        self.call('EL:FixedStatPick')
        self.assertEqual(self.tiles['p_capacity'], 'p_300')
        self.assertNotIn('待核对',self.tiles['p_capacity_status'])
        self.assertRegex(self.tiles['p_row0'], r'^ZE1 \| \d+W$')
        self.assertIn('点击生成时设置', self.tiles['p_template_status'])
        self.assertEqual(self.writes, [])

    def test_elstat_opens_panel_without_any_model_pick(self):
        self.h.builtins['EL:PICKMODEL'] = lambda *args: self.fail('picked before button')
        self.actions = [lambda: self.done(0)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.dialogs, ['el_panel'])
        self.assertIn('拾取配电箱', self.tiles['p_error'])
        self.assertEqual(self.writes, [])

    def test_pick_button_closes_initial_panel_before_model_pick(self):
        events = []
        self.h.builtins['EL:FIXEDSTATPICK'] = lambda: events.append('pick')
        self.actions = [lambda: (events.append('panel'), self.done(9))]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(events, ['panel', 'pick'])
        self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))
        self.assertEqual(self.writes, [])

    def test_elstat_pick_action_reaches_recognized_panel(self):
        self.actions = [lambda: self.done(9), lambda: self.done(0)]
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.dialogs, ['el_panel', 'el_panel'])
        self.assertRegex(self.tiles['p_row0'], r'^ZE1 \| \d+W$')
        self.assertEqual(self.writes, [])

    def test_existing_panel_returns_repick_request_without_saving(self):
        self.actions = [lambda: self.done(9)]
        edited = self.dialog()
        self.assertTrue(truth(self.get('pick-panel', edited)))
        self.assertEqual(self.writes, [])

    def test_default_capacity_generates_without_extra_confirmation(self):
        self.h.builtins['EL:TEMPLATEREADY']=lambda *args:True
        def action():
            self.call('EL:PanelGenerate')
            self.assertEqual(self.closed,2)
            self.assertTrue(truth(self.call('EL:SelectionsReady',self.h.lookup('*EL:PANELDRAFT*'),Symbol('CAP300'))))
        self.actions = [action]
        edited = self.dialog()
        self.assertEqual(self.get('capacity',edited),Symbol('CAP300'))
        self.assertEqual(self.get('capacity-source',self.get('result',edited)),Symbol('DEFAULT'))
        self.assertTrue(truth(self.get('generate',edited)))

    def unknown_local_power(self):
        snapshot = self.h.run("""'((root . "library-fixture/") (catalog (schema . EL_DEVICE_LIBRARY_V1) (library-id . "LIB-EMPTY") (revision . 0) (next-id . 1) (devices)) (index) (present))""")
        self.h.builtins['EL:DLSNAPSHOT'] = lambda: snapshot
        self.h.set('*EL:DLSESSIONSNAPSHOT*', snapshot)
        prepared = self.call('EL:DLPrepare', self.result, self.powers, snapshot, None)
        self.result = self.get('result', prepared)
        self.result = self.call('EL:DLSetOverride', self.result, 'LAMP', Symbol('WATTS'), 5)
        self.result = self.call('EL:DLSetOverride', self.result, 'LAMP', Symbol('WATTS-SET'), True)

    def test_filled_power_generates_without_touching_non_ground_checkbox(self):
        self.unknown_local_power()
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: True
        self.h.builtins['ALERT'] = lambda message: self.fail(message)
        def generate():
            self.assertEqual(self.tiles['b_ground0'], '0')
            self.assertNotIn('待确认', self.tiles['p_error'])
            self.call('EL:PanelGenerate')
            self.assertEqual(self.closed, 2)
        self.actions = [generate]
        edited = self.dialog()
        self.assertTrue(truth(self.get('generate', edited)))
        draft = self.get('result', edited)
        self.assertFalse(truth(self.get('is-ground', self.get('circuits', draft)[0])))
        self.assertFalse(truth(self.get('ground-set', self.call('EL:DLOverride', 'LAMP', draft))))
        self.assertEqual(self.writes, [])

    def test_unknown_ground_can_be_checked_unchecked_and_reopened(self):
        self.unknown_local_power()
        def edit():
            self.call('EL:PanelBlockGround', 0, '1')
            self.assertTrue(truth(self.get('is-ground', self.get('circuits', self.h.lookup('*EL:PANELDRAFT*'))[0])))
            self.call('EL:PanelBlockGround', 0, '0')
            self.call('EL:PanelAccept')
        self.actions = [edit]
        saved = self.get('result', self.dialog())
        record = self.call('EL:DLPersist', saved, self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial')))
        record = self.call('EL:StoreDecode', self.call('EL:StoreEncode', record))
        self.result = self.call('EL:DLRestoreRecord', self.call('EL:RecognizeFixed', self.cfg, 'panel'), record)
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: True
        def reopen():
            self.assertEqual(self.tiles['b_ground0'], '0')
            self.call('EL:PanelGenerate')
            self.assertEqual(self.closed, 2)
        self.actions = [reopen]
        self.assertTrue(truth(self.get('generate', self.dialog())))

    def test_pick_enters_panel_with_all_circuits_without_exit_confirmation(self):
        self.h.builtins['EL:REVIEWFIXEDEXITS'] = lambda *args: self.fail('extra exit confirmation')
        self.actions = [lambda: self.done(0)]
        self.call('EL:FixedStatPick')
        self.assertEqual(self.dialogs, ['el_panel'])
        self.assertNotIn('f_exits', self.tiles)
        self.assertEqual(self.writes, [])

    def test_unvisited_ground_rows_default_to_non_ground_when_generating(self):
        self.unknown_local_power()
        snapshot = self.get('snapshot', self.result)
        sample = self.get('blocks', snapshot)[0]
        blocks = []
        powers = None
        for i in range(10):
            name = f'TYPE{i}'
            block = self.call('EL:Put', Symbol('ID'), f'D{i}', sample)
            block = self.call('EL:Put', Symbol('NAME'), name, block)
            block = self.call('EL:Put', Symbol('ROLE'), Symbol('DEVICE'), block)
            block = self.call('EL:Put', Symbol('IDENTITY'), [name, None, 'block-name-v1'], block)
            blocks.append(block)
            self.result = self.call('EL:DLSetOverride', self.result, name, Symbol('WATTS'), 1)
            self.result = self.call('EL:DLSetOverride', self.result, name, Symbol('WATTS-SET'), True)
            powers = self.call('EL:Put', name, 1, powers)
        circuit = self.get('circuits', self.result)[0]
        circuit = self.call('EL:Put', Symbol('DEVICES'), [f'D{i}' for i in range(10)], circuit)
        self.result = self.call('EL:Put', Symbol('CIRCUITS'), [circuit], self.result)
        self.result = self.call('EL:Put', Symbol('SNAPSHOT'), self.call('EL:Put', Symbol('BLOCKS'), blocks, snapshot), self.result)
        self.powers = powers
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: True
        def generate():
            self.assertIn('1 / 2', self.tiles['f_page'])
            self.assertEqual(len(self.h.lookup('*EL:THUMBROWS*')), 10)
            self.call('EL:PanelGenerate')
            self.assertEqual(self.closed, 2)
        self.actions = [generate]
        draft = self.get('result', self.dialog())
        self.assertTrue(truth(self.get('can-generate', draft)))
        self.assertEqual(self.get('box-watts', draft), 10)
        self.assertFalse(truth(self.get('is-ground', self.get('circuits', draft)[0])))
        self.assertEqual(self.writes, [])

    def test_fixed_update_changed_candidates_opens_panel_without_exit_confirmation(self):
        store = self.call('EL:StoreInitial')
        record = self.call('EL:NewRecord', 'panel', store)
        record = self.call('EL:Put', Symbol('ENGINE'), Symbol('FIXED'), record)
        record = self.call('EL:Put', Symbol('CONFIG'), self.cfg, record)
        record = self.call('EL:Put', Symbol('POWERS'), self.powers, record)
        record = self.call('EL:Put', Symbol('CANDIDATE-KEYS'), [['old-wire', Symbol('OUTLET')]], record)
        store = self.call('EL:StorePutDiagram', record, store)
        tag = [Pair(Symbol('DRAWING'), self.get('drawing-uuid', store)),
               Pair(Symbol('DIAGRAM'), self.get('diagram-id', record)),
               Pair(Symbol('ROLE'), Symbol('PANEL')), Pair(Symbol('UID'), 'panel'), Pair(Symbol('SELF'), 'managed')]
        self.entities['managed'] = [Pair(5, 'managed')]
        captured = []
        self.h.builtins.update({
            'EL:STOREREAD': lambda: store,
            'EL:PICKENTITY': lambda *args: ['managed', [0., 0., 0.]],
            'EL:DIAGRAMTAG': lambda entity: tag if entity == 'managed' else None,
            'EL:REVIEWFIXEDEXITS': lambda *args: self.fail('extra exit confirmation on update'),
            'EL:EDITPANEL': lambda result, cfg: captured.append(result),
        })
        self.h.run('(c:ELUPDATE)')
        self.assertEqual(len(captured), 1)
        self.assertEqual(len(self.get('circuits', captured[0])), 1)
        self.assertFalse(truth(self.get('excluded-seeds', captured[0])))
        self.assertEqual(self.dialogs, [])
        self.assertEqual(self.writes, [])

    def test_library_navigation_preserves_current_circuit_and_does_not_generate(self):
        def action():
            self.h.set('*EL:PANELINDEX*',1)
            self.done(11)
        self.actions=[action]
        context=self.get('library-panel',self.dialog())
        self.assertEqual(self.get('index',self.get('position',context)),1)
        self.assertEqual(self.get('powers',context),self.powers)
        self.assertFalse(truth(self.get('generate',context)))
        self.assertEqual(self.writes,[])
        self.h.set('*EL:DLPANELPOSITION*',self.get('position',context))
        def resumed():
            self.assertEqual(self.h.lookup('*EL:PANELINDEX*'),1)
            self.done(0)
        self.actions=[resumed]
        self.dialog()
        self.assertFalse(truth(self.h.lookup('*EL:DLPANELPOSITION*')))
        self.assertEqual(self.writes,[])

    def test_locked_library_button_reaches_recovery_without_discarding_preview(self):
        captures = []
        self.h.builtins['EL:THUMBCAPTURE'] = lambda block: captures.append(block)
        self.h.builtins['EL:DLROOT'] = lambda: 'library/'
        self.h.builtins['VL-STRING-RIGHT-TRIM'] = lambda chars, text: text.rstrip(chars)
        self.h.builtins['FINDFILE'] = lambda path: path if path == 'library/.write-lock' else None
        self.h.builtins['ALERT'] = lambda _: self.fail('blocking alert on library button')
        def action():
            self.h.set('*EL:PANELINDEX*', 1)
            before = len(captures)
            self.call('EL:DLPanelOpen')
            self.assertEqual(self.closed, 11)
            self.assertEqual(self.h.lookup('*EL:PANELINDEX*'), 1)
            self.assertEqual(len(captures), before)
        self.actions = [action]
        self.dialog()
        self.assertEqual(self.dialogs, ['el_panel'])
        self.assertEqual(self.writes, [])

    def test_locked_library_save_persists_local_draft_without_generation(self):
        persisted = [None]
        def write(value): persisted[0] = value; return True
        def unavailable(_): return self.call('EL:DLFail', '设备库存在占用文件')
        self.h.builtins.update({'EL:DLSNAPSHOT': lambda: None,
            'EL:DLSNAPSHOTLOAD': unavailable, 'EL:DLROOT': lambda: 'library/',
            'EL:STOREREAD': lambda: persisted[0], 'EL:STOREWRITE': write,
            'EL:TRANSACTION': lambda fn,args: self.h.call(fn,args),
            'EL:FRESHRESULT': lambda *args: True,
            'EL:SYNCDIAGRAM': lambda *args: self.fail('offline save changed diagram')})
        def accept():
            self.tiles['b_watts0'] = '7'
            self.call('EL:PanelAccept')
            self.assertEqual(self.closed, 1)
        self.actions = [accept, lambda: self.done(0)]
        self.call('EL:EditPanel', self.result, self.cfg)
        record = self.call('EL:DiagramForPanel', 'panel', persisted[0])
        self.assertEqual(self.call('EL:Get', 'LAMP', self.get('powers', record)), 7)
        self.assertEqual(self.get('status', record), Symbol('STALE'))
        self.assertTrue(truth(self.get('load-error', self.get('device-library', record))))
        self.assertFalse(truth(self.get('panel-output-handle', record)))

    def test_locked_library_generation_gives_actionable_message_without_writes(self):
        alerts = []
        self.h.builtins.update({'EL:DLSNAPSHOT': lambda: None,
            'EL:DLSNAPSHOTLOAD': lambda _: self.call('EL:DLFail', '设备库存在占用文件'),
            'EL:DLROOT': lambda: 'library/', 'ALERT': alerts.append})
        def generate():
            self.call('EL:PanelGenerate')
            self.assertIsNone(self.closed)
            self.assertIn('独立设备库', alerts[-1])
            self.assertIn('草稿', alerts[-1])
            self.done(0)
        self.actions = [generate]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(self.writes, [])

    def test_recover_library_return_and_save_preserve_input_and_reuse_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = self.get('catalog', self.h.builtins['EL:DLSNAPSHOT']())
            root = library_backend.DeviceLibraryTests.fs(self, folder)
            Path(folder, 'catalog.eld').write_text(library_backend.printer(catalog), encoding='utf-8')
            Path(folder, '.write-lock').write_bytes(b'op-old\r\n')
            persisted, captures, callbacks = [None], [], {}
            def write(value): persisted[0] = value; return True
            self.h.builtins.update({'EL:DLROOT': lambda: root,
                'EL:DLSNAPSHOT': lambda: self.call('EL:DLSnapshotLoad', root),
                'EL:STOREREAD': lambda: persisted[0], 'EL:STOREWRITE': write,
                'EL:TRANSACTION': lambda fn,args: self.h.call(fn,args),
                'EL:FRESHRESULT': lambda *args: True,
                'EL:SYNCDIAGRAM': lambda *args: self.fail('draft changed system diagram'),
                'EL:THUMBCAPTURE': lambda block: captures.append(block),
                'ACTION_TILE': lambda k,v: callbacks.__setitem__(k,v),
                'VL-STRING-RIGHT-TRIM': lambda chars,text: text.rstrip(chars),
                'OPEN': lambda p,m,*encoding: open(p,m,encoding='ascii') if m == 'r' and Path(p).is_file() else None,
                'ALERT': lambda msg: self.fail(msg)})
            first_count = []
            def open_library():
                self.tiles['b_watts0'] = '7'
                self.call('EL:PanelCapacity', 'p_600')
                self.h.set('*EL:PANELINDEX*', 1)
                first_count.append(len(captures))
                self.h.run(callbacks['b_library'])
            def recover():
                self.assertEqual(self.dialogs[-1], 'el_device_library_locked')
                self.tiles['dl_lock_confirm'] = '1'
                self.h.run(callbacks['dl_lock_recover'])
            def close_manager():
                self.assertEqual(self.dialogs[-1], 'el_device_library')
                self.h.run(callbacks['dl_close'])
            def save():
                self.assertEqual(self.tiles['b_watts0'], '7')
                self.assertEqual(self.tiles['p_capacity'], 'p_600')
                self.assertEqual(self.h.lookup('*EL:PANELINDEX*'), 1)
                self.assertEqual(len(captures), first_count[0])
                self.h.run(callbacks['accept'])
            self.actions = [open_library, recover, close_manager, save, lambda: self.done(0)]
            self.call('EL:EditPanel', self.result, self.cfg)
            record = self.call('EL:DiagramForPanel', 'panel', persisted[0])
            self.assertEqual(self.call('EL:Get', 'LAMP', self.get('powers', record)), 7)
            self.assertEqual(self.get('draft-capacity', record), Symbol('CAP600'))
            self.assertFalse(truth(self.get('load-error', self.get('device-library', record))))
            self.assertTrue(Path(folder, 'lock-recovered-op-test.txt').exists())

    def test_library_roundtrip_reuses_previews_and_prepared_draft_on_success_or_error(self):
        for outcome in ('closed', 'failed', 'error'):
            with self.subTest(outcome=outcome):
                self.setUp()
                captures, preparations = [], []
                original = self.h.functions['EL:PREPAREDRESULT']
                def prepare(*args):
                    preparations.append(True)
                    return self.h.call([Symbol('LAMBDA'), original[0], *original[1]], list(args))
                def library():
                    if outcome == 'error': raise RuntimeError('library failed')
                    return True if outcome == 'closed' else None
                self.h.builtins.update({'EL:THUMBCAPTURE': lambda block: captures.append(block),
                    'EL:PREPAREDRESULT': prepare, 'EL:DLUIOPEN': library})
                count = []
                def opening():
                    self.h.set('*EL:PANELINDEX*', 1)
                    count.append(len(captures))
                    self.done(11)
                def resumed():
                    self.assertEqual(len(captures), count[0])
                    self.assertEqual(len(preparations), 1)
                    self.assertEqual(self.h.lookup('*EL:PANELINDEX*'), 1)
                    self.done(0)
                self.actions = [opening, resumed]
                self.call('EL:EditPanel', self.result, self.cfg)
                self.assertEqual(self.writes, [])
                self.assertFalse(truth(self.h.lookup('*EL:THUMBSOURCES*')))

    def test_generate_callback_intent_survives_generic_accept_return(self):
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: True
        self.actions = [lambda: (self.call('EL:PanelGenerate'), self.done(1))]
        self.assertTrue(truth(self.get('generate', self.dialog())))

    def test_generate_callback_error_keeps_dialog_and_explains_failure(self):
        events, alerts = [], []
        self.h.builtins['EL:LOGEVENT'] = lambda name, data: events.append((name, data))
        self.h.builtins['ALERT'] = alerts.append
        def broken():
            raise RuntimeError('injected generation callback failure')
        self.h.builtins['EL:PANELSTORESELECTIONS'] = broken
        def action():
            self.call('EL:PanelGenerate')
            self.assertIsNone(self.closed)
            self.assertIsNone(self.h.lookup('*EL:PANELACTION*'))
            self.done(0)
        self.actions = [action]
        self.assertFalse(self.dialog())
        self.assertTrue(any(name == 'PANEL_GENERATE_ERROR' for name, _ in events))
        self.assertIn('injected generation callback failure', alerts[0])
        self.assertEqual(self.writes, [])

    def test_save_records_all_pages_without_changing_checkbox_values(self):
        def action():
            self.h.run("(setq cs (EL:Get 'circuits *EL:PanelDraft*) c (car cs) n 2) (repeat 9 (setq cs (append cs (list (EL:Put 'id (strcat \"R\" (itoa n)) c))) n (1+ n))) (setq *EL:PanelDraft* (EL:Put 'circuits cs *EL:PanelDraft*))")
            self.call('EL:PanelGround', 0, '1')
            self.call('EL:PanelPage', 8)
            self.call('EL:PanelGround', 8, '1')
            self.call('EL:PanelAccept')
        self.actions = [action]
        edited = self.dialog()
        circuits = self.get('circuits', self.get('result', edited))
        self.assertGreater(len(circuits), 8)
        self.assertTrue(all(self.get('ground-source', c) == Symbol('MANUAL') for c in circuits))
        self.assertTrue(truth(self.get('is-ground', circuits[0])))
        self.assertTrue(truth(self.get('is-ground', circuits[8])))
        self.assertFalse(truth(self.get('is-ground', circuits[1])))

    def test_cancelled_setup_returns_to_same_draft_without_saving(self):
        def capture(cfg):
            self.capture_calls.append(cfg)
            return None
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = capture
        def first():
            self.tiles['b_watts0'] = '7'
            self.confirm()
            self.call('EL:PanelGenerate')
        def second():
            self.assertEqual(self.tiles['b_watts0'], '7')
            self.assertEqual(self.tiles['p_capacity'], 'p_600')
            self.assertRegex(self.tiles['p_row0'], r'^ZE1 \| \d+W$')
            self.done(1)
        self.actions = [first, second]
        edited = self.dialog()
        self.assertEqual(len(self.capture_calls), 1)
        self.assertEqual(len(self.dialogs), 2)
        self.assertEqual(self.call('EL:Get', 'LAMP', self.get('powers', edited)), 7)
        self.assertIsNone(self.get('template', self.get('config', edited)))
        self.assertEqual(self.writes, [])

    def test_escape_during_setup_returns_to_panel_and_preserves_draft(self):
        def capture(cfg):
            raise RuntimeError('Function cancelled')
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = capture
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate')), lambda: self.done(0)]
        self.assertIsNone(self.dialog())
        self.assertEqual(len(self.dialogs), 2)
        self.assertIn('返回统计面板', ''.join(self.messages))
        self.assertEqual(self.writes, [])

    def test_successful_setup_returns_new_config_for_generation_without_repick(self):
        template = self.h.run("'((template-test . \"new\"))")
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: template
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate'))]
        edited = self.dialog()
        self.assertTrue(truth(self.get('generate', edited)))
        self.assertEqual(self.get('template', self.get('config', edited)), template)
        self.assertEqual(len(self.dialogs), 1)
        self.assertEqual(self.writes, [])

    def test_valid_template_is_reused_without_setup(self):
        self.h.builtins['EL:TEMPLATEREADY'] = lambda *args: True
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: self.fail('valid template must be reused')
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate'))]
        self.assertTrue(truth(self.get('generate', self.dialog())))

    def test_captured_config_reaches_sync_with_confirmed_choices(self):
        template = self.h.run("'((template-test . \"captured\"))")
        self.h.builtins['EL:CAPTUREFIXEDTEMPLATE'] = lambda cfg: template
        self.h.builtins['EL:TEMPLATEREADY'] = lambda value, cfg: value == template
        self.h.builtins['EL:SIMPLELOADPOWERS'] = lambda: self.h.run("'((version . 1) (powers (\"LAMP\" . 5)))")
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: True
        synced = []
        commands = []
        def cckk2():
            commands.append(self.h.lookup('*EL:CCKK2REQUEST*'))
            del self.h.builtins['C:CCKK2']
            try:
                return self.h.run('(c:CCKK2)')
            finally:
                self.h.builtins['C:CCKK2']=cckk2
        self.h.builtins['C:CCKK2']=cckk2
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: synced.append(args) or True
        self.h.builtins['EL:SAVEDRAFT'] = lambda *args: True
        self.h.builtins['EL:SAVENAMEPOWERS'] = lambda *args: True
        self.actions = [lambda: (self.confirm(), self.call('EL:PanelGenerate'))]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(synced), 1)
        self.assertEqual(len(commands),1)
        self.assertIsNone(self.h.lookup('*EL:CCKK2REQUEST*'))
        result, cfg, powers, capacity, generate, interactive = synced[0]
        self.assertEqual(self.get('template', cfg), template)
        self.assertEqual(capacity, Symbol('CAP600'))
        self.assertTrue(truth(self.call('EL:SelectionsReady', result, capacity)))
        self.assertTrue(truth(generate))

    def test_capacity_and_manual_no_restore_from_saved_draft(self):
        self.h.frames[0]['RESULT'] = self.result
        self.h.run("(setq saved (EL:Put 'ground-source 'manual (car (EL:Get 'circuits result))))")
        saved = self.h.lookup('SAVED')
        record = self.h.run("'((diagram-id . \"d\") (draft-capacity . cap600) (draft-capacity-source . manual))")
        record = self.call('EL:Put', Symbol('DRAFT-CIRCUITS'), [saved], record)
        record = self.call('EL:Put', Symbol('ROWS'), [saved], record)
        fresh = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        prepared = self.call('EL:PreparedResult', fresh, record)
        self.assertEqual(self.get('capacity-source', prepared), Symbol('MANUAL'))
        self.assertEqual(self.get('ground-source', self.get('circuits', prepared)[0]), Symbol('MANUAL'))
        self.assertFalse(truth(self.get('is-ground', self.get('circuits', prepared)[0])))

    def test_save_capacity_then_recognize_same_panel(self):
        persisted = [None]
        def write(value):
            persisted[0] = value
            return True
        self.h.builtins.update({
            'EL:STOREREAD': lambda: persisted[0],
            'EL:STOREWRITE': write,
            'EL:TRANSACTION': lambda fn, args: self.h.call(fn, args),
            'EL:SAVENAMEPOWERS': lambda *args: True,
        })
        for tile,capacity,source in ((None,'CAP300','DEFAULT'),('p_600','CAP600','MANUAL'),('p_1000','CAP1000','MANUAL')):
            with self.subTest(capacity=capacity):
                def accept():
                    if tile:self.call('EL:PanelCapacity',tile)
                    self.call('EL:PanelAccept')
                self.actions=[accept, lambda: self.done(0)]
                self.call('EL:EditPanel',self.result,self.cfg)
                record=self.call('EL:DiagramForPanel','panel',persisted[0])
                self.assertEqual(self.get('draft-capacity',record),Symbol(capacity))
                self.assertEqual(self.get('draft-capacity-source',record),Symbol(source))
                fresh=self.call('EL:RecognizeFixed',self.cfg,'panel')
                self.actions=[lambda:self.done(0)]
                self.call('EL:EditPanel',fresh,self.cfg)
                self.assertEqual(self.tiles['p_capacity'],tile or 'p_300')

    def test_save_complete_statistics_without_template_still_saves_draft(self):
        self.h.builtins['EL:SIMPLELOADPOWERS'] = lambda: self.h.run("'((version . 1) (powers (\"LAMP\" . 5)))")
        self.h.builtins['EL:FRESHRESULT'] = lambda *args: True
        stored = []
        self.h.builtins['EL:SAVEDRAFT'] = lambda *args: stored.append(args) or True
        self.h.builtins['EL:SAVENAMEPOWERS'] = lambda *args: True
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: self.fail('missing template cannot sync')
        self.actions = [lambda: self.done(1), lambda: self.done(0)]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0][3],Symbol('CAP300'))

    def test_save_returns_to_same_page_with_values_and_preview_without_picking(self):
        captures, saves = [], []
        self.h.builtins.update({
            'EL:THUMBCAPTURE': lambda block: captures.append(block),
            'EL:FRESHRESULT': lambda *args: True,
            'EL:SAVEDRAFT': lambda *args: saves.append(args) or True,
            'EL:SAVENAMEPOWERS': lambda *args: True,
            'EL:SYNCDIAGRAM': lambda *args: self.fail('save must not sync output'),
            'EL:INVOKECCKK2': lambda *args: self.fail('save must not generate'),
            'EL:PICKONE': lambda *args: self.fail('save must not pick'),
        })
        counts = []
        def save():
            self.tiles['b_watts0'] = '7'
            self.call('EL:PanelCapacity', 'p_600')
            self.h.set('*EL:PANELINDEX*', 1)
            counts.append(len(captures))
            self.call('EL:PanelAccept')
        def resumed():
            self.assertEqual(self.tiles['b_watts0'], '7')
            self.assertEqual(self.tiles['p_capacity'], 'p_600')
            self.assertEqual(self.h.lookup('*EL:PANELINDEX*'), 1)
            self.assertEqual(len(captures), counts[0])
            self.assertEqual(len(saves), 1)
            self.done(0)
        self.actions = [save, resumed]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(self.actions, [])
        self.assertEqual(self.dialogs, ['el_panel', 'el_panel'])

    def test_failed_save_returns_to_panel_with_input_for_retry(self):
        self.h.builtins.update({'EL:FRESHRESULT': lambda *args: True,
            'EL:SAVEDRAFT': lambda *args: None, 'EL:SAVENAMEPOWERS': lambda *args: True})
        def save():
            self.tiles['b_watts0'] = '9'
            self.call('EL:PanelAccept')
        def resumed():
            self.assertEqual(self.tiles['b_watts0'], '9')
            self.done(0)
        self.actions = [save, resumed]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(self.actions, [])

    def test_save_existing_diagram_marks_draft_pending_with_one_write(self):
        store = self.call('EL:StoreInitial')
        record = self.call('EL:NewRecord', 'panel', store)
        record = self.call('EL:Put', Symbol('PANEL-OUTPUT-HANDLE'), 'old-output', record)
        persisted = [self.call('EL:StorePutDiagram', record, store)]
        writes = []
        def write(value):
            persisted[0] = value
            writes.append(value)
            return True
        self.h.builtins.update({'EL:STOREREAD': lambda: persisted[0], 'EL:STOREWRITE': write,
            'EL:TRANSACTION': lambda fn,args: self.h.call(fn,args),
            'EL:FRESHRESULT': lambda *args: True,
            'EL:SYNCDIAGRAM': lambda *args: self.fail('save changed generated diagram')})
        self.actions = [lambda: self.call('EL:PanelAccept'), lambda: self.done(0)]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(writes), 1)
        saved = self.call('EL:DiagramForPanel', 'panel', persisted[0])
        self.assertEqual(self.get('panel-output-handle', saved), 'old-output')
        self.assertEqual(self.get('status', saved), Symbol('STALE'))
        self.assertEqual(self.get('stale-reason', saved), Symbol('DRAFT-SAVED'))

    def test_shared_sync_accepts_default_ground_without_confirmation(self):
        self.h.builtins['EL:STOREREAD'] = lambda: None
        self.h.builtins['EL:MARKSTALE'] = lambda *args: self.fail('default ground must not mark stale')
        self.h.builtins['EL:TRANSACTION'] = lambda *args: self.fail('non-generating sync must not mutate DWG')
        result = self.call('EL:PanelCompute', self.result, self.powers, self.cfg)
        self.assertTrue(truth(self.call('EL:SyncDiagram', result, self.cfg, self.powers, Symbol('CAP300'), None, None)))
        self.assertNotIn('尚未确认', ''.join(self.messages))

    def test_legacy_generation_retains_capacity_fallback_without_fixed_review(self):
        self.h.frames[0]['*EL:RESULT*'] = self.call('EL:Put', Symbol('ENGINE'), Symbol('LEGACY'), self.result)
        self.h.builtins['EL:BOXSTATISTICS'] = lambda result, *args: result
        self.h.builtins['EL:LOADLIBRARY'] = lambda: None
        self.h.builtins['EL:EDITPANEL'] = lambda *args: self.fail('legacy path must remain separate')
        synced = []
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: synced.append(args)
        self.h.run('(c:ELGEN)')
        self.assertEqual(len(synced), 1)
        self.assertEqual(synced[0][3], Symbol('CAP300'))

    def test_prepared_record_template_is_reused_for_same_box(self):
        template = self.h.run("'((test-template . \"saved\"))")
        record = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        record = self.call('EL:Put', Symbol('CONFIG'), self.call('EL:Put', Symbol('TEMPLATE'), template, self.cfg), record)
        store = self.call('EL:StorePutDiagram', record, self.call('EL:StoreInitial'))
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['EL:TEMPLATEREADY'] = lambda value, cfg: value == template
        self.actions = [lambda: self.done(0)]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertIn('模板已验证', self.tiles['p_template_status'])

    def test_drawing_template_cache_is_reused_for_other_box(self):
        template = self.h.run("'((test-template . \"drawing-cache\"))")
        store = self.call('EL:Put', Symbol('FIXED-TEMPLATE'), template, self.call('EL:StoreInitial'))
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['EL:TEMPLATEREADY'] = lambda value, cfg: value == template
        self.actions = [lambda: self.done(0)]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertIn('模板已验证', self.tiles['p_template_status'])

    def test_cancelled_review_preserves_old_choices_and_marks_output_unupdated(self):
        record = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        record = self.call('EL:Put', Symbol('PANEL-OUTPUT-HANDLE'), 'old-output', record)
        record = self.call('EL:Put', Symbol('CAPACITY-OPTION'), Symbol('CAP300'), record)
        store = self.call('EL:StorePutDiagram', record, self.call('EL:StoreInitial'))
        self.h.builtins['EL:STOREREAD'] = lambda: store
        self.h.builtins['EL:TRANSACTION'] = lambda fn, args: self.h.call(fn, args)
        self.h.builtins['EL:SYNCDIAGRAM'] = lambda *args: self.fail('cancel must not change output')
        self.actions = [lambda: (self.confirm(), self.done(0))]
        self.call('EL:EditPanel', self.result, self.cfg)
        self.assertEqual(len(self.writes), 1)
        stored = self.call('EL:DiagramForPanel', 'panel', self.writes[0])
        self.assertEqual(self.get('capacity-option', stored), Symbol('CAP300'))
        self.assertEqual(self.get('panel-output-handle', stored), 'old-output')
        self.assertEqual(self.get('stale-reason', stored), Symbol('REVIEW-CANCELLED'))
        self.assertIsNone(self.get('draft-capacity', stored))


class SelectionStoreTests(unittest.TestCase):
    def setUp(self):
        db.StoreTests.setUp(self)
        for name in ('config', 'geometry', 'topology', 'statistics', 'generation', 'fixed', 'panel', 'diagram-update', 'diagram-commands'):
            self.h.load_definitions(db.ROOT / 'src' / f'{name}.lsp')
        self.h.builtins['EL:TRANSACTION'] = lambda fn, args: self.h.call(fn, args)
        self.h.builtins['EL:TEMPLATEREADY'] = lambda template, cfg: truth(template)

    def test_draft_confirmation_and_shared_template_roundtrip_through_xrecord(self):
        self.h.run('''(setq cfg '((template (name . "captured"))))
          (setq result '((panel . "source") (engine . fixed) (capacity-source . manual) (can-generate . T)
            (circuits ((id . "R1") (seed (key "wire" outlet)) (circuit-uid . "u1")
              (seed-key "wire" outlet) (is-ground) (ground-source . manual)))))
          (EL:SaveDraft result cfg nil 'cap600)
          (setq result nil cfg nil)
          (setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))''')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"), Symbol('CAP600'))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"), Symbol('MANUAL'))
        self.assertEqual(self.h.run("(EL:Get 'ground-source (car (EL:Get 'draft-circuits reopened)))"), Symbol('MANUAL'))
        self.assertIsNone(self.h.run("(EL:Get 'is-ground (car (EL:Get 'draft-circuits reopened)))"))
        self.assertEqual(self.h.run("(EL:Get 'name (EL:Get 'fixed-template (EL:StoreRead)))"), 'captured')

    def test_missing_capacity_and_ground_use_defaults_without_marking_stale(self):
        self.h.run('''(EL:SaveDraft '((panel . "source") (engine . fixed) (can-generate . T)
          (circuits ((id . "R1") (seed-key "wire" outlet) (ground-source . default)))) nil nil nil)
          (setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))''')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"),Symbol('CAP300'))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"),Symbol('DEFAULT'))
        self.assertNotEqual(self.h.run("(EL:Get 'status reopened)"), Symbol('STALE'))
        self.assertIsNone(self.h.run("(EL:Get 'is-ground (car (EL:Get 'draft-circuits reopened)))"))


if __name__ == '__main__':
    unittest.main()
