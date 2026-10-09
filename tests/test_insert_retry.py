"""Insertion confirmation and retry state. Date: 2026-10-09."""
import unittest
from autolisp_host import Host, Symbol, truth
import test_fixed_diagnostics as diag
import test_diagram_store as db


class ConfirmationTests(unittest.TestCase):
    def test_yes_case_enter_and_explicit_no(self):
        h = Host()
        h.load_definitions(db.ROOT / 'src/diagram-store.lsp')
        for answer, expected in [('Yes', True), ('YES', True), ('yes', True),
                                 ('Y', True), (None, True), ('No', False), ('no', False)]:
            h.builtins.update({'INITGET': lambda *args: None,
                              'GETKWORD': lambda prompt, answer=answer: answer})
            self.assertEqual(truth(h.run('(EL:ConfirmDiagram)')), expected)


class RetryTests(unittest.TestCase):
    setUp = diag.FixedDiagnosticTests.setUp
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get
    line = diag.FixedDiagnosticTests.line
    block = diag.FixedDiagnosticTests.block
    plan = diag.FixedDiagnosticTests.plan
    logging = diag.FixedDiagnosticTests.logging

    def test_cancelled_first_insert_keeps_accepted_config_and_draft_before_retry(self):
        result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        result = self.call('EL:Put', Symbol('CAN-GENERATE'), True, result)
        cfg = self.call('EL:Put', Symbol('TEMPLATE'), 'accepted-template', self.cfg)
        edited = self.h.run("'((powers (\"LAMP\" . 5)) (capacity . cap600) (generate . T))")
        edited = self.call('EL:Put', Symbol('RESULT'), result,
                           self.call('EL:Put', Symbol('CONFIG'), cfg, edited))
        events = []
        self.h.builtins.update({
            'EL:PANELDIALOG': lambda *args: edited,
            'EL:TEMPLATEREADY': lambda *args: True,
            'EL:SELECTIONSREADY': lambda *args: True,
            'EL:FRESHRESULT': lambda *args: True,
            'EL:SAVENAMEPOWERS': lambda *args: True,
            'EL:REMEMBERPANELPOWERS': lambda *args: True,
            'EL:SAVEDRAFT': lambda *args: events.append(('draft', args[1])) or True,
            'EL:SYNCDIAGRAM': lambda *args: events.append(('preview-cancelled', args[1])) or None,
        })
        self.call('EL:EditPanel', result, self.cfg)
        self.assertEqual([e[0] for e in events], ['draft', 'preview-cancelled'])
        self.assertEqual(events[0][1], cfg)
        self.assertEqual(self.h.lookup('*EL:FIXEDCONFIG*'), cfg)
        self.assertEqual(self.h.lookup('*EL:RESULT*'), result)


if __name__ == '__main__':
    unittest.main()
