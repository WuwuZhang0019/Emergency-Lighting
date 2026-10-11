"""Preview visibility must not change wire identity. Date: 2026-10-11."""
import unittest
from pathlib import Path
from autolisp_host import Host
class VisibilitySignatureTests(unittest.TestCase):
    def setUp(self):
        self.h=Host()
        self.h.load_definitions(Path(__file__).resolve().parents[1]/'src/geometry.lsp')
    def test_implicit_and_explicit_visible_are_equal(self):
        a=self.h.run('(EL:CanonicalVisibilityDXF \'((0 . "LINE") (10 1.0 2.0 0.0)))')
        b=self.h.run('(EL:CanonicalVisibilityDXF \'((0 . "LINE") (60 . 0) (10 1.0 2.0 0.0)))')
        self.assertEqual(a,b)
    def test_hidden_and_changed_geometry_remain_different(self):
        a=self.h.run('(EL:CanonicalVisibilityDXF \'((0 . "LINE") (10 1.0 2.0 0.0)))')
        for data in ('((0 . "LINE") (60 . 1) (10 1.0 2.0 0.0))','((0 . "LINE") (10 2.0 2.0 0.0))'):
            self.assertNotEqual(a,self.h.run('(EL:CanonicalVisibilityDXF \''+data+')'))
