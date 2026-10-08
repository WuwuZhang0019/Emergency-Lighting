import importlib.util
import json
import pathlib
import unittest
import test_cad_adapter
from autolisp_host import Pair, Symbol, truth

ROOT=pathlib.Path(__file__).resolve().parent


class FixtureTests(unittest.TestCase):
    def test_fixture_topology_matches_rule10_expected_load_and_incomplete_state(self):
        adapter = test_cad_adapter.CadAdapterTests()
        adapter.setUp()
        h = adapter.h
        h.load_definitions(ROOT.parent / 'src/statistics.lsp')
        values = (ROOT/'fixtures/cad-plan.dxf').read_text().splitlines()
        tags = list(zip(map(int, values[::2]), values[1::2]))
        records, current = [], []
        for code, value in tags:
            if code == 0 and current:
                records.append(current)
                current = []
            current.append((code, value))
        records.append(current)
        section = block_name = previous = None
        for index, record in enumerate(records):
            typ = record[0][1]
            raw = dict(record)
            if typ == 'SECTION':
                section = raw[2]
                continue
            if typ == 'ENDSEC':
                section = None
                continue
            if section not in ('BLOCKS', 'ENTITIES'):
                continue
            handle = f'fixture-{index}'
            data = [Pair(0, typ), Pair(5, handle), Pair(410, 'Model')]
            for n, (code, value) in enumerate(record[1:], 1):
                if code in (10, 11):
                    coords = dict(record[n + 1:n + 3])
                    data.append(Pair(code, [float(value), float(coords.get(code+10, 0)), float(coords.get(code+20, 0))]))
                elif code in (2, 8):
                    data.append(Pair(code, value))
                elif code in (40, 41, 42, 43, 50):
                    data.append(Pair(code, float(value)))
                elif code in (70, 90):
                    data.append(Pair(code, int(value)))
            if typ == 'BLOCK':
                block_name, previous = raw[2], None
                adapter.blocks[block_name] = data
                continue
            adapter.entities[handle] = data
            if section == 'BLOCKS':
                if previous:
                    adapter.next_entity[previous] = handle
                else:
                    adapter.blocks[block_name].append(Pair(-2, handle))
                previous = handle
            else:
                adapter.selected.append(handle)

        cfg = h.run('''(EL:Put 'device-names '("ELA_LAMP" "ELA_SIGN")
            (EL:Put 'panel-names '("ELA_BOX") (EL:Put 'wire-layers '("ELA_WIRE")
            (EL:Put 'device-layers '("ELA_DEVICE") (EL:Put 'panel-layers '("ELA_PANEL") cfg)))))''')
        snap = adapter.call('EL:CollectEndpointSnapshot', cfg)
        panel = next(adapter.get('id', b) for b in adapter.get('blocks', snap)
                     if adapter.get('role', b) == Symbol('PANEL'))
        physical = adapter.call('EL:BuildPhysical', snap, cfg, panel)
        seeds = adapter.call('EL:SeedCandidates', adapter.get('snapshot', physical), cfg, panel)
        result = adapter.call('EL:AnalyzeSnapshot', snap, cfg, panel, seeds)
        powers = []
        for block in adapter.get('blocks', snap):
            if adapter.get('role', block) != Symbol('DEVICE'):
                continue
            watts = 5 if adapter.get('name', block) == 'ELA_LAMP' else 1
            powers.append([Pair(Symbol('IDENTITY'), adapter.get('identity', block)),
                           Pair(Symbol('DISPLAY'), adapter.get('name', block)),
                           Pair(Symbol('CATEGORY'), Symbol('LIGHTING' if watts == 5 else 'SIGN')),
                           Pair(Symbol('WATTS'), watts)])
        cfg = adapter.call('EL:Put', Symbol('POWERS'), powers, cfg)
        stats = adapter.call('EL:BoxStatistics', result, cfg, None, None)
        expected = json.loads((ROOT/'fixtures/cad-plan.expected.json').read_text())
        self.assertEqual(adapter.get('box-watts', stats), expected['box_watts_after_category_confirmation'])
        self.assertFalse(truth(adapter.get('complete', result)))
        self.assertFalse(truth(adapter.get('can-generate', stats)))
        self.assertEqual(sorted(adapter.get('watts', c) for c in adapter.get('circuits', stats)), [2, 5, 5])

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
        self.assertEqual(sum(c['watts_after_category_confirmation'] for c in expected['circuits']),12)
        self.assertFalse(expected['complete'])
        self.assertFalse(expected['can_generate'])
        self.assertEqual(expected['circuits'][0]['issue'], 'WIRE_ATTACHED_TO_EQUIPMENT')
        self.assertEqual(sum(code==0 and value=='INSERT' for code,value in tags),6)
