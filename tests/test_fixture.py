import importlib.util
import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parent


class FixtureTests(unittest.TestCase):
    def test_generated_fixture_is_reproducible_and_has_three_outlets(self):
        spec=importlib.util.spec_from_file_location('cad_fixture',ROOT/'fixtures/generate_fixture.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        actual=(ROOT/'fixtures/cad-plan.dxf').read_text()
        self.assertEqual(actual,module.build_dxf())
        values=actual.splitlines()
        self.assertEqual(len(values)%2,0)
        tags=list(zip(map(int,values[::2]),values[1::2]))
        self.assertEqual(tags[-1],(0,'EOF'))
        expected=json.loads((ROOT/'fixtures/cad-plan.expected.json').read_text())
        self.assertEqual(len(expected['circuits']),3)
        self.assertEqual(sum(c['watts_after_category_confirmation'] for c in expected['circuits']),17)
        self.assertEqual(sum(code==0 and value=='INSERT' for code,value in tags),6)
