"""Pending legends must not lock power editing. Date: 2026-10-15. Native CAD pending."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Host, Pair, Symbol, truth
import test_library_autosave as autosave
import test_device_pick as picking

ROOT=Path(__file__).resolve().parents[1]


class CaptureParameterEditingTests(unittest.TestCase):
    def commands(self):
        h=Host()
        for module in ('common','main','device-ui'):
            h.load_definitions(ROOT/'src'/(module+'.lsp'))
        h.builtins['PRINC']=lambda *args:None
        return h

    def test_elstat_always_opens_panel_without_starting_or_resuming_a_legend(self):
        for pending in (None,[Pair(Symbol('TOKEN'),'unfinished-worker')]):
            with self.subTest(pending=bool(pending)):
                h=self.commands(); opened=[]
                h.set('*EL:DLCAPTUREJOB*',pending)
                context=h.run("'((capacity . cap600) (saved-input . \"保留\"))")
                h.set('*EL:DLPARENTCONTEXT*',context)
                h.builtins.update({'EL:FIXEDSTAT':lambda:opened.append('panel'),
                    'C:ELDEVLIB':lambda:self.fail('ELSTAT routed into capture wait'),
                    'EL:DLCAPTURERESUME':lambda *args:self.fail('opening parameters resumed a worker')})
                h.call('C:ELSTAT',[])
                self.assertEqual(opened,['panel'])
                self.assertEqual(h.lookup('*EL:DLCAPTUREJOB*'),pending)
                self.assertEqual(h.lookup('*EL:DLPARENTCONTEXT*'),context)

    def test_eldevlib_opens_editor_for_running_failed_and_completed_markers(self):
        for failed in (None,True):
            with self.subTest(failed=bool(failed)):
                h=self.commands(); opened=[]
                job=[Pair(Symbol('TOKEN'),'unfinished-worker'),Pair(Symbol('FAILED'),failed),
                     Pair(Symbol('MARKER'),'complete.txt')]
                h.set('*EL:DLCAPTUREJOB*',job);h.set('*EL:DLUIPICKREQUESTED*',True)
                h.builtins.update({'EL:DLUIOPEN':lambda:opened.append('library'),
                    'FINDFILE':lambda *args:self.fail('editor opening polled the worker'),
                    'EL:DLCAPTURERESUME':lambda *args:self.fail('editor opening resumed the worker')})
                h.call('C:ELDEVLIB',[])
                self.assertEqual(opened,['library'])
                self.assertEqual(h.lookup('*EL:DLCAPTUREJOB*'),job)
                self.assertIsNone(h.lookup('*EL:DLUIPICKREQUESTED*'))

    def test_only_graph_changing_actions_are_disabled_during_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            f=autosave.LibraryAutosaveTests();f.setUp();f.editor(folder)
            modes={};f.h.builtins['MODE_TILE']=lambda key,value:modes.__setitem__(key,value)
            for pending in (True,None):
                f.h.set('*EL:DLCAPTUREJOB*',pending)
                f.call('EL:DLUIFields')
                for key in ('dl_watts','dl_display','dl_block','dl_aliases','dl_ground','dl_zero','dl_active'):
                    self.assertEqual(modes[key],0,key)
                for key in ('dl_pick','dl_repair','dl_import','dl_directory','dl_new'):
                    self.assertEqual(modes[key],1 if pending else 0,key)

    def test_two_power_edits_and_close_save_while_capture_is_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            f=autosave.LibraryAutosaveTests();f.setUp();f.editor(folder)
            job=[Pair(Symbol('TOKEN'),'still-pending')];f.h.set('*EL:DLCAPTUREJOB*',job)
            for name in ('EL:DLCAPTURESTART','EL:DLCAPTUREFILE','EL:DLCAPTURECLEANUP'):
                f.h.builtins[name]=lambda *args:self.fail('power editing touched a graph task')
            self.assertTrue(truth(f.edit('dl_watts','17')))
            f.call('EL:DLUISelect','1')
            self.assertTrue(truth(f.edit('dl_watts','19')))
            f.call('EL:DLUILeave',0)
            self.assertEqual([f.get('watts',row) for row in f.rows()],[17,19])
            self.assertEqual(f.closed,[0])
            self.assertEqual(f.h.lookup('*EL:DLCAPTUREJOB*'),job)

    def test_late_worker_completion_preserves_already_autosaved_power(self):
        f=picking.DevicePickTests();f.setUp();self.addCleanup(f.doCleanups)
        f.library();f.h.set('*EL:DLUIPICKQUEUE*',['Lamp'])
        f.call('EL:DLUIPickNext')
        job=f.h.lookup('*EL:DLCAPTUREJOB*')
        edited=f.put('watts-text','12',f.put('ground-confirmed',True,f.get('entry',job)))
        edited=f.put('display','已修改的设备名',edited)
        f.call('EL:DLUISetDraft',edited)
        self.assertTrue(truth(f.call('EL:DLUISaveWork')))
        self.assertEqual(f.get('watts',f.call('EL:DLUIEntry')),12)
        f.complete()
        draft=f.call('EL:DLUIEntry')
        self.assertEqual(f.get('watts',draft),12)
        self.assertEqual(f.get('display',draft),'已修改的设备名')
        self.assertIsNotNone(f.get('captured',draft))
        self.assertTrue(truth(f.call('EL:DLUISaveWork')))
        saved=f.get('devices',f.get('catalog',f.call('EL:DLSnapshotLoad',f.root)))[0]
        self.assertEqual(f.get('watts',saved),12)
        self.assertEqual(f.get('display',saved),'已修改的设备名')
        self.assertTrue(truth(f.call('EL:DLEntryAssets',saved)))

    def test_repair_callback_also_keeps_newer_saved_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            f=autosave.LibraryAutosaveTests();f.setUp();f.editor(folder)
            before=f.call('EL:DLUIEntry')
            snapshot=f.get('snapshot',f.h.lookup('*EL:DLUISTATE*'))
            job=[Pair(Symbol('SNAPSHOT'),snapshot),Pair(Symbol('TOKEN'),'repair-worker')]
            completed=f.put('captured',job,before)
            f.edit('dl_watts','23');f.edit('dl_display','新名称')
            f.h.set('*EL:DLUIHOST*',Symbol('PANEL'))
            f.call('EL:DLUIResume',completed)
            draft=f.call('EL:DLUIEntry')
            self.assertEqual(f.get('watts',draft),23)
            self.assertEqual(f.get('display',draft),'新名称')
            self.assertEqual(f.get('captured',draft),job)


if __name__=='__main__':
    unittest.main()
