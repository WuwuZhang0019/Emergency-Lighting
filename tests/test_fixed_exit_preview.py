"""Circuit-color preview fixture. Date: 2026-10-14. Status: current."""
import unittest
from autolisp_host import Symbol
import test_exit_devices as exits
import test_simple_flow as simple


class FixedExitPreviewTests(unittest.TestCase):
    call = exits.ExitDeviceTests.call
    get = exits.ExitDeviceTests.get
    line = exits.ExitDeviceTests.line
    block = exits.ExitDeviceTests.block
    plan = exits.ExitDeviceTests.plan
    logging = exits.ExitDeviceTests.logging

    def setUp(self):
        exits.ExitDeviceTests.setUp(self)
        for name in ('EL:CLEARGAPPREVIEW', 'EL:CLEARPICKHIGHLIGHTS'):
            self.h.builtins.pop(name, None)
        self.visible, self.overlays, self.zooms = set(), [], []
        self.modal = False
        self.h.builtins.update({'REDRAW': self.redraw, 'GRTEXT': lambda *args: None,
            'GRDRAW': self.draw, 'EL:SIMPLEZOOM': self.zoom,
            'GETVAR': lambda key: 150. if key == 'VIEWSIZE' else 100.,
            'GETSTRING': lambda *args: '',
            'VL-CATCH-ALL-ERROR-MESSAGE': lambda error: str(error.exception)})
        for name in ('ENTMOD', 'ENTMAKE', 'ENTMAKEX', 'ENTDEL'):
            self.h.builtins[name] = lambda *args: self.fail('Preview must not modify DWG')

    def redraw(self, entity=None, mode=None):
        self.assertFalse(self.modal)
        if entity is None:
            self.overlays.clear()
        elif mode == 3:
            self.visible.add(entity)
        elif mode == 4:
            self.visible.discard(entity)

    def draw(self, *args):
        self.assertFalse(self.modal)
        self.overlays.append(args)

    def zoom(self, lo, hi):
        self.assertFalse(self.modal)
        self.assertEqual(self.overlays, [])
        self.zooms.append((lo, hi))

    def recognize(self):
        return self.call('EL:RecognizeFixed', self.cfg, 'panel')








if __name__ == '__main__':
    unittest.main()
