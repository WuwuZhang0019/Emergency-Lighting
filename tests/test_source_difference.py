"""Bounded source mismatch evidence. Date: 2026-10-11."""
import unittest
from pathlib import Path
from autolisp_host import Host
from test_diagram_store import dump
class SourceDifferenceTests(unittest.TestCase):
    def test_exact_field_and_values_are_logged(self):
        h=Host();h.load_definitions(Path(__file__).resolve().parents[1]/'src/common.lsp')
        events=[]
        h.builtins.update({'VL-PRIN1-TO-STRING':dump,'EL:LOGEVENT':lambda *a:events.append(a)})
        h.run('(EL:LogSnapshotDifference \'((drawing . "A") (signature . "abc1xyz")) \'((drawing . "A") (signature . "abc2xyz")))')
        self.assertEqual(len(events),1)
        self.assertEqual(events[0][0],'SOURCE_FIELD_DIFFERENCE')
        self.assertIn('abc1xyz',dump(events[0][1]));self.assertIn('abc2xyz',dump(events[0][1]))
    def test_matching_snapshots_do_not_emit_mismatch(self):
        h=Host();h.load_definitions(Path(__file__).resolve().parents[1]/'src/common.lsp')
        h.builtins['EL:LOGEVENT']=lambda *a:self.fail('unexpected mismatch')
        h.run("(EL:LogSnapshotDifference '((drawing . \"A\")) '((drawing . \"A\")))")
