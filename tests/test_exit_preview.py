"""Exit preview leaves modal DCL and preserves review state. Date: 2026-10-08."""
import unittest
from autolisp_host import Symbol, truth
import test_pick_feedback as feedback

class ExitPreviewTests(unittest.TestCase):
    setUp = feedback.PickFeedbackTests.setUp
    redraw = feedback.PickFeedbackTests.redraw
    pick = feedback.PickFeedbackTests.pick
    choice = feedback.PickFeedbackTests.choice
    get = feedback.PickFeedbackTests.get

    def dialog_adapter(self, ending=1):
        self.tiles = {}; self.callbacks = {}; self.modal = False
        self.openings = 0; self.previews = []; self.overlays = []; self.unloaded = []
        self.h.run("""(setq *EL:Root* "package/" *EL:ExitDefaults* nil)
          (setq seeds '(((id . "R1") (wire . "wire") (key "wire" start) (point 0.0 0.0 0.0))
                       ((id . "R2") (wire . "wire2") (key "wire2" start) (point 0.0 2.0 0.0))
                       ((id . "R3") (wire . "panel") (key "panel" start) (point 0.0 4.0 0.0))))
          (setq *EL:ExitSnapshot* '((wires
            ((id . "wire") (segments ((0.0 0.0 0.0) (10.0 0.0 0.0))))
            ((id . "wire2") (segments ((0.0 2.0 0.0) (10.0 2.0 0.0))))
            ((id . "panel") (segments ((0.0 4.0 0.0) (10.0 4.0 0.0)))))))""")
        def graphics(*args):
            self.assertFalse(self.modal, 'Must draw after the dialog returns')
            self.overlays.append(args)
        def redraw(*args):
            self.assertFalse(self.modal, 'Must highlight after the dialog returns')
            return self.redraw(*args)
        def done(status):
            self.modal = False
            return status
        def start():
            self.modal = True
            n=self.openings; self.openings += 1
            if n:
                self.assertEqual(self.tiles['exits'],str(n-1))
                self.assertEqual(self.tiles['scope_exclude'],'1')
                self.assertEqual(self.tiles['role_recheck'],'1')
            if n < 3:
                self.tiles.update(exits=str(n),scope_exclude='1',role_recheck='1')
                self.h.frames[0]['$VALUE']=str(n)
                return self.h.run(self.callbacks['exits'])
            return self.h.run(self.callbacks[{1:'accept',0:'cancel',2:'add_wire'}[ending]])
        def pause(*args):
            self.assertFalse(self.modal)
            self.previews.append(set(self.visible))
            return ''
        self.h.builtins.update({
            'LOAD_DIALOG':lambda *a:1,'NEW_DIALOG':lambda *a:True,
            'START_DIALOG':start,'DONE_DIALOG':done,'UNLOAD_DIALOG':lambda d:self.unloaded.append(d),
            'START_LIST':lambda *a:None,'ADD_LIST':lambda *a:None,'END_LIST':lambda:None,
            'SET_TILE':lambda k,v:self.tiles.update({k:v}),'GET_TILE':lambda k:self.tiles.get(k,''),
            'ACTION_TILE':lambda k,v:self.callbacks.update({k:v}),
            'GETSTRING':pause,'GETVAR':lambda k:60.,'GRDRAW':graphics,
            'TRANS':lambda p,*a:p,'REDRAW':redraw,
        })

    def test_each_row_has_its_own_visible_wire_and_state_survives_reopening(self):
        self.dialog_adapter()
        result=self.h.run('(EL:ReviewExits seeds)')
        self.assertEqual(self.previews,[{'wire'},{'wire2'},{'panel'}])
        self.assertEqual([self.get('id',r) for r in result[0]],['R3'])
        self.assertEqual(len(self.overlays),15)  # one path plus four marker sides per preview
        self.assertTrue(all(call[2]==2 for call in self.overlays))
        self.assertFalse(self.visible)
        self.assertEqual(self.unloaded,[1])
        self.assertIsNone(self.h.lookup('*EL:DIALOGID*'))
        self.assertTrue(truth(self.h.lookup('*EL:SCOPECONFIRMED*')))
        self.assertTrue(truth(self.h.lookup('*EL:REVIEWALLROLES*')))

    def test_cancel_and_add_layer_after_preview_clear_feedback(self):
        for ending in (0,2):
            self.setUp();self.dialog_adapter(ending)
            result=self.h.run('(EL:ReviewExits seeds)')
            self.assertEqual(result, None if ending==0 else Symbol('ADD'))
            self.assertFalse(self.visible)
            self.assertEqual(self.unloaded,[1])

    def test_bulk_selection_does_not_draw_inside_modal_dialog(self):
        self.dialog_adapter()
        self.h.run('(setq *EL:ExitRows* seeds)')
        self.modal=True
        self.h.run('(EL:SelectAllExits)')
        self.assertEqual(self.tiles['exits'],'0 1 2 ')
        self.assertEqual(self.overlays,[])
        self.tiles['exits']=''
        self.assertIsNone(self.h.run('(EL:RequestExitPreview "")'))
        self.assertTrue(self.modal)
