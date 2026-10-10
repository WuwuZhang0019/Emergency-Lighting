"""Two-pick device table and persistent block powers. Date: 2026-10-08."""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_cad_adapter as adapter
import test_root_init as roots

class SimpleFlowTests(unittest.TestCase):
    call = adapter.CadAdapterTests.call
    get = adapter.CadAdapterTests.get
    line = adapter.CadAdapterTests.line
    block = adapter.CadAdapterTests.block

    def setUp(self):
        adapter.CadAdapterTests.setUp(self)
        for name in ('statistics','main','simple','diagram-update'):
            self.h.load_definitions(adapter.ROOT/'src'/f'{name}.lsp')
        self.cfg=self.h.lookup('CFG')

    def network(self):
        snapshot=self.call('EL:SimpleCollect',self.cfg)
        return self.call('EL:SimpleNetwork',snapshot,self.cfg,'panel')

    def plan(self):
        self.block('BOX','P','panel',[0.,0.,0.])
        self.block('LAMP','D','a',[10.,0.,0.])
        self.block('LAMP','D','b',[5.,6.,0.])
        self.block('LAMP','D','remote',[110.,0.,0.])
        self.line('w1',[1.,0.,0.],[9.,0.,0.],'W')
        self.line('w2',[5.,0.,0.],[5.,5.,0.],'W')
        self.line('wr',[101.,0.,0.],[109.,0.,0.],'W')
        self.selected=['panel','a','b','remote','w1','w2','wr']

    def test_connected_system_joins_t_branches_and_groups_without_roles(self):
        self.plan()
        result=self.network()
        self.assertEqual(sorted(self.get('id',b) for b in self.get('devices',result)),['a','b'])
        rows=self.call('EL:SimpleRows',self.get('devices',result),None)
        self.assertEqual(len(rows),1)
        self.assertEqual(self.get('count',rows[0]),2)
        self.assertIsNone(self.get('watts',rows[0]))

    def gap_plan(self, target_start=(20.,0.,0.), target_end=(29.,0.,0.), device=(30.,0.,0.)):
        self.block('BOX','P','panel',[0.,0.,0.])
        self.block('LAMP','D','after',list(device))
        self.line('before',[1.,0.,0.],[10.,0.,0.],'W')
        self.line('after-wire',list(target_start),list(target_end),'W')
        self.selected=['panel','after','before','after-wire']

    def test_free_gap_ends_reconnect_when_opposite_ends_touch_panel_and_device(self):
        self.gap_plan()
        result=self.network()
        self.assertEqual([self.get('id',b) for b in self.get('devices',result)],['after'])
        ends=self.get('ends',self.get('snapshot',result))
        for key in (['before',Symbol('END')],['after-wire',Symbol('START')]):
            ep=self.call('EL:By',Symbol('KEY'),key,ends)
            self.assertTrue(truth(self.call('EL:GapEligible',ep)))
        self.assertEqual(len(self.get('gap-pairs',result)),1)

    def test_multiple_breaks_continue_past_middle_device_and_t_branch(self):
        self.gap_plan(target_end=(30.,0.,0.),device=(50.,0.,0.))
        self.block('LAMP','D','middle',[5.,0.,0.])
        self.block('LAMP','D','branch',[25.,10.,0.])
        self.line('last',[40.,0.,0.],[49.,0.,0.],'W')
        self.line('branch-wire',[25.,0.,0.],[25.,9.,0.],'W')
        self.selected += ['middle','branch','last','branch-wire']
        result=self.network()
        self.assertEqual(sorted(self.get('id',b) for b in self.get('devices',result)),['after','branch','middle'])
        self.assertEqual(len(self.get('gap-pairs',result)),2)
        rows=self.call('EL:SimpleRows',self.get('devices',result),None)
        self.assertEqual(self.get('count',rows[0]),3)

    def test_endpoint_on_device_does_not_continue_to_remote_wire(self):
        self.gap_plan()
        self.block('LAMP','D','terminal',[10.,0.,0.]);self.selected.append('terminal')
        result=self.network()
        self.assertEqual([self.get('id',b) for b in self.get('devices',result)],['terminal'])
        self.assertFalse(self.get('gap-pairs',result))
        ep=self.call('EL:By',Symbol('KEY'),['before',Symbol('END')],self.get('ends',self.get('snapshot',result)))
        self.assertTrue(truth(self.get('occupied',ep)))

    def test_gap_does_not_jump_to_parallel_other_elevation_or_out_of_range_wire(self):
        for y,z,x in ((0.2,0.,20.),(0.,2.,20.),(0.,0.,2011.)):
            with self.subTest(y=y,z=z,x=x):
                self.setUp()
                self.gap_plan((x,y,z),(x+9.,y,z),(x+10.,y,z))
                self.assertFalse(self.get('devices',self.network()))

    def test_noncollinear_crossing_in_gap_is_not_a_connection_or_blocker(self):
        self.gap_plan()
        self.line('cross',[15.,-5.,0.],[15.,5.,0.],'W')
        self.block('LAMP','D','cross-device',[15.,6.,0.]);self.selected += ['cross','cross-device']
        result=self.network()
        self.assertEqual([self.get('id',b) for b in self.get('devices',result)],['after'])
        self.assertNotIn('cross',self.get('wire-ids',result))

    def test_block_inside_gap_is_not_skipped_by_wire_bounds_filter(self):
        self.gap_plan()
        self.block('LAMP','D','obstacle',[15.,0.,0.]);self.selected.append('obstacle')
        result=self.network()
        self.assertFalse(self.get('devices',result))
        issues=self.get('gap-issues',result)
        reasons=[self.get('reason',rejected) for issue in issues
                 for rejected in (self.get('rejected',self.get('detail',issue)) or [])]
        self.assertIn(Symbol('BLOCKED_BY_DEVICE_OR_PATH'),reasons)

    def test_bent_polylines_continue_along_the_actual_broken_end_direction(self):
        self.gap_plan(device=(30.,25.,0.))
        for name,points in (('before',[(1.,0.),(5.,0.),(5.,10.)]),
                            ('after-wire',[(5.,20.),(5.,25.),(29.,25.)])):
            self.entities[name]=[Pair(0,'LWPOLYLINE'),Pair(5,name),Pair(8,'W'),Pair(410,'Model'),
                Pair(90,len(points)),Pair(70,0),Pair(38,0.),Pair(210,[0.,0.,1.])]+[
                Pair(10,list(point)) for point in points]
        result=self.network()
        self.assertEqual([self.get('id',b) for b in self.get('devices',result)],['after'])
        self.assertEqual(len(self.get('gap-pairs',result)),1)

    def test_gap_log_records_endpoint_coordinates_candidates_and_pair_count(self):
        self.gap_plan();events=[]
        self.h.frames[0]['*EL:LOGACTIVE*']=True
        self.h.builtins['EL:LOGEVENT']=lambda stage,detail:events.append((stage,detail))
        self.network()
        summary=[detail for stage,detail in events if stage=='SIMPLE_GAPS'][0]
        self.assertEqual(self.get('paired-gaps',summary),1)
        self.assertEqual(self.get('open-ends',summary),2)
        self.assertEqual(self.get('max-distance',summary),2000.)
        entries=[detail for stage,detail in events if stage=='SIMPLE_GAP_END']
        self.assertEqual(len(entries),2)
        self.assertEqual(sorted(self.get('point',ep)[0] for ep,row in entries),[10.,20.])
        self.assertTrue(all(len(self.get('candidates',row))==1 for ep,row in entries))

    def test_other_wire_layer_and_bare_crossing_do_not_merge_systems(self):
        self.plan()
        self.line('w2',[5.,-5.,0.],[5.,5.,0.],'W') # two interiors cross without an endpoint
        result=self.network()
        self.assertEqual([self.get('id',b) for b in self.get('devices',result)],['a'])
        self.line('w2',[5.,0.,0.],[5.,5.,0.],'OTHER')
        self.assertEqual([self.get('id',b) for b in self.get('devices',self.network())],['a'])

    def test_whole_block_middle_crossing_connects_and_never_reads_contents(self):
        self.block('BOX','P','panel',[0.,0.,0.]);self.block('LAMP','D','a',[10.,0.,0.])
        self.line('w',[-5.,0.,0.],[15.,0.,0.],'W');self.selected=['panel','a','w']
        def forbidden(*args): self.fail('Internal block geometry or role review invoked')
        for name in ('ENTNEXT','EL:BLOCKCONTOUR','EL:DEFINITIONDATA','EL:CLOSEDRINGS','EL:REVIEWROLES','EL:REVIEWEXITS',
                     'EL:COLLECTENDPOINTSNAPSHOT','EL:LOADROLELIBRARY','EL:DYNAMICSTATE'):
            self.h.builtins[name]=forbidden
        self.assertEqual([self.get('id',b) for b in self.get('devices',self.network())],['a'])

    def test_collection_does_not_parse_outside_wire_layers(self):
        self.plan();self.line('outside',[0.,100.,0.],[100.,100.,0.],'OTHER');self.selected.append('outside')
        self.h.functions[Symbol('TEST:WIRERECORD')]=self.h.functions[Symbol('EL:WIRERECORD')];seen=[]
        def record(entity,cfg):
            seen.append(entity)
            return self.call('TEST:WireRecord',entity,cfg)
        self.h.builtins['EL:WIRERECORD']=record
        self.network()
        self.assertEqual(set(seen),{'w1','w2','wr'})

    def test_legacy_summary_one_pick_and_one_table_then_remembers_powers(self):
        self.plan();picks=[];tables=[];written=[];files={}
        self.h.frames[0]['*EL:ROOT*']='package/'
        def pick(prompt):
            picks.append(prompt)
            self.assertLessEqual(len(picks),1)
            return ['panel' if len(picks)==1 else 'w2',[0.,0.,0.]]
        def table(result,rows):
            tables.append(rows)
            return [self.call('EL:Put',Symbol('WATTS'),7,r) for r in rows]
        def write(path,data):
            written.append((path,data));files[path]=data;return True
        def forbidden(*args): self.fail('No exit, role or category confirmation is permitted')
        self.h.builtins.update({'EL:ENSUREROOT':lambda:True,'ENTSEL':pick,'EL:SIMPLEDIALOG':table,
            'FINDFILE':lambda p:p if p in files else None,'EL:WRITEDATA':write,
            'EL:READDATA':lambda p:files.get(p),
            'REDRAW':lambda *a:None,'HANDENT':lambda x:x,'PRINC':lambda *a:None,
            'EL:REVIEWROLES':forbidden,'EL:REVIEWEXITS':forbidden,'EL:POWERDIALOG':forbidden})
        self.h.run('(EL:SimpleStat)')
        self.assertEqual(len(picks),1);self.assertEqual(len(tables),1)
        self.assertEqual(self.get('count',tables[0][0]),2)
        self.assertEqual(len(written),1)
        self.assertTrue(written[0][0].endswith('config/block-powers.eld'))
        self.assertEqual(self.get('total-watts',self.h.lookup('*EL:DEVICERESULT*')),14.)
        self.assertIsNone(self.h.lookup('*EL:RESULT*'))
        picks.clear()
        self.h.run('(EL:SimpleStat)')
        self.assertEqual(len(picks),1);self.assertEqual(len(tables),2)
        self.assertEqual(self.get('watts',tables[1][0]),7)
        # Cancelled edits must not replace the saved per-block value.
        self.h.builtins['EL:SIMPLEDIALOG']=lambda *args:None
        self.h.run('(c:ELPOWER)')
        self.assertEqual(len(written),2)

    def test_power_edit_requires_valid_values_and_keeps_zero(self):
        self.plan();rows=self.call('EL:SimpleRows',self.get('devices',self.network()),None)
        self.h.frames[0]['*EL:SIMPLEROWS*']=rows;self.h.frames[0]['*EL:SIMPLEINDEX*']=0
        tiles={'s_edit':'-1'};done=[]
        self.h.builtins.update({'GET_TILE':lambda k:tiles.get(k,''),'SET_TILE':lambda k,v:tiles.update({k:v}),
                              'DONE_DIALOG':lambda v:done.append(v)})
        self.h.run('(EL:SimpleAccept)');self.assertEqual(done,[])
        tiles['s_edit']='';self.h.run('(EL:SimpleAccept)');self.assertEqual(done,[])
        tiles['s_edit']='0';self.h.run('(EL:SimpleAccept)');self.assertEqual(done,[1])
        self.assertEqual(self.call('EL:SimpleTotal',self.h.lookup('*EL:SIMPLEROWS*')),0.)

    def test_dialog_preview_restores_current_row_and_unsaved_values(self):
        self.plan();result=self.network();rows=self.call('EL:SimpleRows',self.get('devices',result),None)
        self.h.frames[0]['TEST:RESULT']=result;self.h.frames[0]['TEST:ROWS']=rows
        self.h.frames[0]['*EL:ROOT*']='package/'
        tiles={};callbacks={};modal=[False];opens=[];draws=[];zooms=[]
        def start():
            modal[0]=True;opens.append(1)
            if len(opens)==1:
                tiles['s_edit']='6';return self.h.run(callbacks['s_locate'])
            self.assertEqual(tiles['s_edit'],'6')
            return self.h.run(callbacks['accept'])
        def done(code): modal[0]=False;return code
        def draw(*args):
            self.assertFalse(modal[0]);draws.append(args)
        def zoom(app,lo,hi):
            self.assertFalse(modal[0]);zooms.append((lo,hi))
        self.h.builtins.update({'LOAD_DIALOG':lambda *a:1,'NEW_DIALOG':lambda *a:True,
            'START_DIALOG':start,'DONE_DIALOG':done,'UNLOAD_DIALOG':lambda *a:None,
            'START_LIST':lambda *a:None,'ADD_LIST':lambda *a:None,'END_LIST':lambda:None,
            'SET_TILE':lambda k,v:tiles.update({k:v}),'GET_TILE':lambda k:tiles.get(k,''),
            'ACTION_TILE':lambda k,v:callbacks.update({k:v}),'GETSTRING':lambda *a:'',
            'GETVAR':lambda *a:60.,'REDRAW':draw,'GRDRAW':draw,'TRANS':lambda p,*a:p,
            'VLA-ZOOMWINDOW':zoom,'VLAX-GET-ACAD-OBJECT':lambda:'app','VLAX-3D-POINT':lambda p:p,
            'HANDENT':lambda x:x,'PRINC':lambda *a:None,'GRTEXT':lambda *a:None})
        edited=self.h.run('(EL:SimpleDialog test:result test:rows)')
        self.assertEqual(self.get('watts',edited[0]),6)
        self.assertTrue(draws);self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))
        self.assertEqual(len(zooms),1)
        self.assertLess(zooms[0][0][0],4.)
        self.assertGreater(zooms[0][1][0],11.)

class SimplePersistenceTests(unittest.TestCase):
    def test_file_reload_and_merge_preserve_unrelated_block_types(self):
        r=roots.RootFixture();r.setUp();self.addCleanup(r.doCleanups)
        r.h.frames[0]['*EL:ROOT*']=r.root
        self.assertTrue(truth(r.h.run("(EL:SimpleSavePowers '(((key . \"LAMP\") (watts . 5)) ((key . \"SIGN\") (watts . 1))))")))
        path=r.package/'config/block-powers.eld';self.assertTrue(path.is_file())
        # Load actual saved data again, then update only one type.
        self.assertTrue(truth(r.h.run("(EL:SimpleSavePowers '(((key . \"LAMP\") (watts . 7))))")))
        powers=r.h.run("(EL:Get 'powers (EL:SimpleLoadPowers))")
        self.assertEqual(r.h.call(Symbol('EL:GET'),['LAMP',powers]),7)
        self.assertEqual(r.h.call(Symbol('EL:GET'),['SIGN',powers]),1)
        self.assertNotIn('drawing',path.read_text(encoding='utf-8').lower())

    def test_corrupt_power_file_is_not_overwritten(self):
        r=roots.RootFixture();r.setUp();self.addCleanup(r.doCleanups)
        r.h.frames[0]['*EL:ROOT*']=r.root
        path=r.package/'config/block-powers.eld';path.write_text('(broken)',encoding='utf-8')
        self.assertFalse(truth(r.h.run("(EL:SimpleSavePowers '(((key . \"LAMP\") (watts . 5))))")))
        self.assertEqual(path.read_text(encoding='utf-8'),'(broken)')
