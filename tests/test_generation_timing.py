"""Generation preparation timing and catch boundaries. Date: 2026-10-21.

Status: focused adapter checks; synthetic clocks do not measure native CAD speed.
"""
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol, truth
import test_cckk_panel_command as native


ROOT = Path(__file__).resolve().parents[1]


class GenerationTimingTests(unittest.TestCase):
    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def field(self, name, data):
        return self.call('EL:Get', Symbol(name.upper()), data)

    def stage(self, name):
        return self.call('EL:Get', name, self.h.lookup('*EL:PERFSTAGES*'))

    def test_real_save_and_generation_keep_plan_output_and_measure_preparation(self):
        f = native.PanelCommandTests()
        f.setUp()
        f.two_circuits()
        self.h = f.h
        clock = [0]
        old_getvar = self.h.builtins['GETVAR']
        self.h.functions[Symbol('TEST:PREPARED')] = self.h.functions[Symbol('EL:PREPAREDRESULT')]
        self.h.functions[Symbol('TEST:PLAN')] = self.h.functions[Symbol('EL:FIXEDPLANBUILD')]

        def prepare(*args):
            clock[0] += 13
            return self.call('TEST:PREPARED', *args)

        def plan(*args):
            clock[0] += 7
            return self.call('TEST:PLAN', *args)

        self.h.builtins.update({
            'GETVAR': lambda key: clock[0] if key == 'MILLISECS' else old_getvar(key),
            'EL:PREPAREDRESULT': prepare,
            'EL:FIXEDPLANBUILD': plan,
        })
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertTrue(truth(self.h.run("(EL:SaveDraft result cfg nil 'cap300)")))
        self.h.frames[0]['*EL:PLACEMENTONLY*'] = True
        self.assertTrue(truth(f.invoke()))
        f.assert_two_circuit_output()
        self.assertEqual(self.field('calls', self.stage('SAVE_GENERATION_DRAFT')), 1)
        self.assertEqual(self.field('calls', self.stage('GENERATION_SOURCE_VERIFY')), 2)
        self.assertEqual(self.field('inclusive-ms', self.stage('GENERATION_PREPARE')), 13)
        self.assertEqual(self.field('inclusive-ms', self.stage('GENERATION_CONTEXT')), 13)
        self.assertEqual(self.field('calls', self.stage('GENERATION_PLAN')), 2)
        self.assertEqual(self.field('inclusive-ms', self.stage('GENERATION_PLAN')), 14)
        self.assertEqual(self.field('calls', self.stage('GENERATION_RECORD')), 1)
        rows = self.h.lookup('*EL:MONITORROWS*')
        child = next(r for r in rows if self.field('stage', r) == 'GENERATION_PREPARE')
        context = next(r for r in rows if self.field('stage', r) == 'GENERATION_CONTEXT')
        self.assertEqual(self.field('parent-id', child), self.field('id', context))
        rebuild = next(r for r in rows if self.field('stage', r) == 'PLACEMENT_PLAN_REBUILD')
        after = next(r for r in rows if self.field('stage', r) == 'GENERATION_PLAN'
                     and self.field('parent-id', r) == self.field('id', rebuild))
        self.assertEqual(self.field('elapsed-ms', after), 7)
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)

    def test_caught_template_error_closes_only_its_frame_and_restores_input_clock(self):
        self.h = Host()
        for name in ('common', 'generation', 'fixed'):
            self.h.load_definitions(ROOT / 'src' / (name + '.lsp'))
        clock = [0]

        def fail(*args):
            clock[0] += 17
            raise RuntimeError('template native error')

        self.h.builtins.update({
            'GETVAR': lambda key: clock[0] if key == 'MILLISECS' else 20261021.12,
            'EL:FIXEDTEMPLATE': lambda *_: True,
            'EL:FIXEDTEXT': lambda: 'text-spec',
            'TBLSEARCH': lambda *_: True,
            'EL:TEMPLATERUNTIMECHECK': fail,
        })
        self.h.run("(setq template '((layer . \"SYS_系统标注_E\") "
                   "(circuit (states ((text . \"text-spec\"))))))")
        self.call('EL:PerfStart', 'ELSTAT')
        outer = self.call('EL:PerfBegin', 'USER_INPUT')
        checkpoint = self.h.lookup('*EL:PERFPENDING*')
        self.assertIsNone(self.h.run('(EL:TemplateReady template nil)'))
        self.assertEqual(self.h.lookup('*EL:PERFPENDING*'), checkpoint)
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 1)
        self.assertEqual(self.field('interrupted', self.stage('TEMPLATE_VALIDATE')), 1)
        self.assertEqual(self.field('program-ms', self.stage('TEMPLATE_VALIDATE')), 17)
        clock[0] += 23
        self.call('EL:PerfEnd', outer, Symbol('RETURNED'))
        self.assertEqual(self.call('EL:PerfWaiting'), 23)
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))

    def test_panel_submit_preparation_excludes_dialog_wait_and_input_save(self):
        f = native.PanelCommandTests()
        f.setUp()
        f.two_circuits()
        self.h = f.h
        clock = [0]
        old_getvar = self.h.builtins['GETVAR']
        result, cfg = self.h.lookup('RESULT'), self.h.lookup('CFG')
        edited = [Pair(Symbol('RESULT'), result), Pair(Symbol('CONFIG'), cfg),
                  Pair(Symbol('CAPACITY'), Symbol('CAP300'))]
        self.h.functions[Symbol('TEST:SAVE')] = self.h.functions[Symbol('EL:SAVEDRAFTWORK')]

        def dialog_wait():
            clock[0] += 100
            return edited

        def remember(*args):
            clock[0] += 11

        def save(*args):
            clock[0] += 23
            return self.call('TEST:SAVE', *args)

        self.h.builtins.update({
            'GETVAR': lambda key: clock[0] if key == 'MILLISECS' else old_getvar(key),
            'EL:LOGEVENT': lambda *_: None,
            'EL:DLSNAPSHOT': lambda: None,
            'EL:DLPREPARE': lambda value, powers, *_: [Pair(Symbol('RESULT'), value),
                                                     Pair(Symbol('POWERS'), powers)],
            'EL:TEMPLATEREADY': lambda *_: True,
            'EL:PANELDIALOG': lambda *_: self.call('EL:PerfInput', Symbol('TEST:DIALOG'), []),
            'TEST:DIALOG': dialog_wait,
            'EL:REMEMBERPANELPOWERS': remember,
            'EL:SAVENAMEPOWERS': lambda *_: True,
            'EL:SAVEDRAFTWORK': save,
        })
        self.call('EL:PerfStart', 'ELSTAT')
        self.h.frames[0]['*EL:LOGACTIVE*'] = True
        self.call('EL:EditPanelOnce', result, cfg)
        self.assertEqual(self.field('inclusive-ms', self.stage('PANEL_SUBMIT_PREPARE')), 11)
        self.assertEqual(self.field('inclusive-ms', self.stage('SAVE_GENERATION_DRAFT')), 23)
        self.assertEqual(self.call('EL:PerfWaiting'), 100)
        self.assertTrue(truth(self.call('EL:Get', 'panel-submit', self.h.lookup('*EL:PERFMARKS*'))))
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)


if __name__ == '__main__':
    unittest.main()
