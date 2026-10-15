"""Locate saved power parameters without publishing unsaved edits. Date: 2026-10-15."""
from pathlib import Path, PureWindowsPath
import unittest
from autolisp_host import Host, Symbol
import test_post_stat_workflow as workflow

ROOT=Path(__file__).resolve().parents[1]


class LibraryLocationTests(unittest.TestCase):
    def setUp(self):
        self.h=Host()
        for name in ('common','config','device-ui'):
            self.h.load_definitions(ROOT/'src'/(name+'.lsp'))
        self.root='C:/中文 设备库/'; self.path=self.root+'catalog.eld'
        self.present=True; self.directory=True; self.opened=[]
        self.h.run("""(setq *EL:DLUIState* '((snapshot (root . "C:/中文 设备库/"))
          (drafts ("ELDEV1" (watts-text . "未保存功率")))))""")
        self.h.builtins.update({
            'VL-FILE-DIRECTORY-P':lambda path:self.directory and path==self.root,
            'VL-STRING-RIGHT-TRIM':lambda chars,value:value.rstrip(chars),
            'FINDFILE':lambda path:path if self.present and path==self.path else None,
            'VL-STRING-TRANSLATE':lambda old,new,value:value.translate(str.maketrans(old,new)),
            'STARTAPP':lambda app,args:self.opened.append((app,args)) or 1,
        })

    def call(self):
        return self.h.call(Symbol('EL:DLOPENCATALOG'),[])

    def test_selects_catalog_of_current_editor_and_keeps_raw_drafts(self):
        before=self.h.lookup('*EL:DLUISTATE*')
        self.assertIn('已选中 catalog.eld',self.call())
        self.assertEqual(self.opened,[('explorer.exe','/select,"'+str(PureWindowsPath(self.path))+'"')])
        self.assertEqual(self.h.lookup('*EL:DLUISTATE*'),before)

    def test_missing_catalog_opens_directory_and_explains_save_requirement(self):
        self.present=False
        self.assertIn('尚未生成',self.call())
        self.assertEqual(self.opened,[('explorer.exe','"'+self.root.replace('/',chr(92))+'"')])

    def test_missing_directory_does_not_open_a_different_library(self):
        self.directory=False
        self.assertIn('不存在',self.call())
        self.assertEqual(self.opened,[])

    def test_launcher_failure_is_a_notice_and_does_not_change_library(self):
        self.h.builtins['STARTAPP']=lambda *args:None
        before=self.h.lookup('*EL:DLUISTATE*')
        self.assertIn('无法打开',self.call())
        self.assertEqual(self.h.lookup('*EL:DLUISTATE*'),before)


class LibraryLocationDialogTests(unittest.TestCase):
    def fixture(self):
        f=workflow.PostStatWorkflowTests(); f.setUp()
        callbacks={}; opens=[]
        f.h.builtins['ACTION_TILE']=lambda key,action:callbacks.__setitem__(key,action)
        f.h.builtins['EL:DLOPENCATALOG']=lambda:opens.append(True) or '已定位 catalog.eld'
        return f,callbacks,opens

    def test_panel_open_keeps_capacity_and_unsaved_power_without_saving_catalog(self):
        f,callbacks,opens=self.fixture()
        def edit():
            f.tiles['dl_display']='保留设备编辑'; f.tiles['dl_watts']='12'
            f.call('EL:PanelCapacity','p_600')
            f.invoke_action(callbacks,'dl_open')
        f.actions=[edit,lambda:f.invoke_action(callbacks,'cancel')]
        f.dialog()
        self.assertEqual(opens,[True]); self.assertEqual(f.dialogs,['el_panel','el_panel'])
        self.assertEqual(f.tiles['p_capacity'],'p_600')
        self.assertEqual(f.get('watts-text',f.call('EL:DLUIDraft')),'12')
        self.assertEqual(f.get('display',f.call('EL:DLUIDraft')),'保留设备编辑')

    def test_standalone_open_returns_to_same_editor_with_unsaved_power(self):
        f,callbacks,opens=self.fixture()
        f.call('EL:DLUIPanelBegin',f.call('EL:DLSnapshot'))
        def edit():
            f.tiles['dl_watts']='17'; f.tiles['dl_display']='独立窗口编辑'
            f.invoke_action(callbacks,'dl_open')
        f.actions=[edit,lambda:f.invoke_action(callbacks,'dl_close')]
        f.call('EL:DLUIRun')
        self.assertEqual(opens,[True]); self.assertEqual(f.dialogs,['el_device_library','el_device_library'])
        self.assertEqual(f.get('watts-text',f.call('EL:DLUIDraft')),'17')
        self.assertEqual(f.get('display',f.call('EL:DLUIDraft')),'独立窗口编辑')


if __name__=='__main__':
    unittest.main()
