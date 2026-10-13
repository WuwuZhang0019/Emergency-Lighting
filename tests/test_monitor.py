"""Focused action timeline checks. Date: 2026-10-13. Synthetic clock, not CAD timing."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Host, Symbol, truth
from test_root_init import lisp_data

ROOT = Path(__file__).resolve().parents[1]


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(ROOT / 'src/common.lsp')
        self.clock = 0
        self.handles = []
        self.h.builtins.update({
            'GETVAR': lambda key: self.clock if key == 'MILLISECS' else 20261013.123456,
            'EL:PERFREPORT': lambda summary: None,
            'VL-SYMBOL-NAME': lambda name: str(name),
            'VL-PRIN1-TO-STRING': lisp_data,
            'VL-STRING-TRANSLATE': lambda old, new, value: value.translate(str.maketrans(old, new)),
            'FINDFILE': lambda path: str(path) if Path(path).exists() else None,
            'VL-MKDIR': lambda path: Path(path).mkdir(exist_ok=True),
            'OPEN': self.open_file,
            'WRITE-LINE': lambda text, file: file.write(text + '\n'),
            'CLOSE': lambda file: file.close(),
        })

    def open_file(self, path, mode, *encoding):
        file = open(path, mode, encoding='utf-8')
        self.handles.append(file)
        return file

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, data):
        return self.call('EL:Get', Symbol(key.upper()), data)

    def test_callback_work_and_nested_input_are_not_charged_to_dialog_wait(self):
        self.call('EL:PerfStart', 'ELSTAT')
        wait = self.call('EL:PerfBegin', 'USER_INPUT')
        self.clock = 100
        self.call('EL:MonitorUIBegin', 'p_generate', '1')
        self.clock = 120
        nested = self.call('EL:PerfBegin', 'USER_INPUT')
        self.clock = 130
        self.call('EL:PerfEnd', nested, Symbol('RETURNED'))
        self.clock = 160
        self.call('EL:MonitorUIEnd')
        self.clock = 200
        self.call('EL:PerfEnd', wait, Symbol('RETURNED'))
        self.assertEqual(self.call('EL:PerfWaiting'), 150)
        rows = self.h.lookup('*EL:MONITORROWS*')
        action = next(r for r in rows if self.get('stage', r) == 'UI_ACTION')
        self.assertEqual(self.get('program-ms', action), 50)
        self.assertEqual(self.get('parent-id', action), self.get('id', wait))

    def test_escaping_callback_unwinds_pause_before_finishing_input(self):
        self.call('EL:PerfStart', 'ELSTAT')
        self.call('EL:PerfBegin', 'USER_INPUT')
        self.clock = 100
        self.call('EL:MonitorUIBegin', 'cancel', '0')
        self.clock = 140
        self.call('EL:PerfUnwind', None)
        self.assertEqual(self.call('EL:PerfWaiting'), 100)
        self.assertEqual(self.h.lookup('*EL:PERFWAITDEPTH*'), 0)
        self.assertTrue(all(self.get('status', r) == Symbol('INTERRUPTED')
                            for r in self.h.lookup('*EL:MONITORROWS*')))

    def test_registered_callback_keeps_value_and_original_dialog_action(self):
        registered = {}
        results = []
        self.h.builtins['ACTION_TILE'] = lambda key, code: registered.__setitem__(key, code)
        self.h.builtins['DONE_DIALOG'] = lambda value: results.append(value)
        self.call('EL:MonitorActionTile', 'p_generate', '(setq chosen $value) (done_dialog 7)')
        self.call('EL:PerfStart', 'ELSTAT')
        self.h.frames[0].update({'$KEY': 'p_generate', '$VALUE': '5'})
        self.h.run(registered['p_generate'])
        self.assertEqual(self.h.lookup('CHOSEN'), '5')
        self.assertEqual(results, [7])
        self.assertFalse(truth(self.h.lookup('*EL:PERFPENDING*')))

    def test_report_contains_loading_actions_exit_and_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            self.h.frames[0]['*EL:ROOT*'] = Path(directory).as_posix() + '/'
            self.call('EL:MonitorLoadBegin', 0)
            self.clock = 15
            self.call('EL:MonitorLoadEnd', Symbol('LOAD-FINISHED'))
            self.clock = 200
            self.call('EL:PerfStart', 'ELSTAT')
            wait = self.call('EL:PerfBegin', 'USER_INPUT')
            self.clock = 300
            self.call('EL:MonitorUIBegin', 'p_generate', '1')
            self.clock = 320
            self.call('EL:MonitorUIEnd')
            self.clock = 350
            self.call('EL:PerfEnd', wait, Symbol('RETURNED'))
            self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
            output = Path(self.h.lookup('*EL:MONITORPATH*'))
            text = output.read_text(encoding='utf-8')
            self.assertIn('日期：2026-10-13', text)
            self.assertIn('最近一次插件加载', text)
            self.assertIn('生成或更新 [p_generate]=1', text)
            self.assertIn('总耗时 0.150 秒；程序 0.020 秒；交互 0.130 秒', text)
            self.assertIn('退出：0.150 秒', text)
            self.assertIn('|2|1|0.100|0.120|0.020|0.020|0.000|', text)
            self.call('EL:PerfStart', 'ELSTAT')
            self.call('EL:PerfFinish', Symbol('COMMAND-FINISHED'))
            self.assertNotEqual(output, Path(self.h.lookup('*EL:MONITORPATH*')))
            self.assertEqual(output.read_text(encoding='utf-8'), text)
            self.assertTrue(all(file.closed for file in self.handles))

    def test_write_failure_closes_file_and_keeps_business_result(self):
        with tempfile.TemporaryDirectory() as directory:
            self.h.frames[0]['*EL:ROOT*'] = Path(directory).as_posix() + '/'
            self.call('EL:PerfStart', 'ELSTAT')
            def fail(*args):
                raise OSError('disk full')
            self.h.builtins['WRITE-LINE'] = fail
            result = self.call('EL:PerfCall', 'TX_WRITE', Symbol('+'), [1, 2])
            self.call('EL:PerfFinish', Symbol('FAILED'))
            self.assertEqual(result, 3)
            self.assertTrue(truth(self.h.lookup('*EL:MONITORLASTROWS*')))
            self.assertFalse(truth(self.h.lookup('*EL:PERFACTIVE*')))
            self.assertTrue(self.handles)
            self.assertTrue(all(file.closed for file in self.handles))


if __name__ == '__main__':
    unittest.main()
