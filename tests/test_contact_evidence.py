"""Exact compact contact dependencies. Date: 2026-10-13.

Finite CAD adapters and typed evidence only; no native AutoCAD timing or acceptance.
"""
import copy
from pathlib import Path
import unittest

from autolisp_host import Host, Pair, Symbol, truth
import test_freshness_reuse as fresh
import test_diagram_store as store


ROOT = Path(__file__).resolve().parents[1]


def pair(key, value):
    return Pair(Symbol(key.upper()), value)


class ContactEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for name in ('common', 'simple'):
            self.h.load_definitions(ROOT / 'src' / f'{name}.lsp')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def shape(self, geometry, handle='A', definition='LARGE', translation=0.):
        matrix = [1., 0., 0., 1., translation, 0., 0., 1.]
        raw = [Pair(2, definition), Pair(10, [translation, 0., 0.]),
               Pair(41, 1.), Pair(42, 1.), Pair(43, 1.), Pair(50, 0.),
               Pair(210, [0., 0., 1.])]
        return geometry + [pair('id', handle),
                           pair('definition-key', [Symbol('DEFINITION'), definition]),
                           pair('definition-geometry', self.call('EL:GeometryFacts', geometry)),
                           pair('instance-transform', [matrix, raw])]

    def evidence(self, shape, handle='A'):
        return self.call('EL:DeviceContactEvidence', [Pair(handle, shape)])

    def geometry(self):
        segments = [[[0., 0., 0.], [1., 0., 0.]]]
        return [pair('segments', segments),
                pair('curves', [[[0., 0., 0.], 1., 0., 6.283185307179586, None]]),
                pair('regions', [segments]),
                pair('holes', [[[[.2, .2, 0.], [.4, .2, 0.]]]]),
                pair('issues', None), pair('sampled-curves', None)]

    def test_eighteen_large_instances_keep_one_complete_typed_definition(self):
        segments = [[[float(i), .125, 0.], [float(i) + .5, .25, 0.]]
                    for i in range(8207)]
        geometry = [pair('segments', segments), pair('curves', None),
                    pair('regions', [segments]), pair('holes', None), pair('issues', None)]

        def bounded_signature(value):
            self.assertEqual(value, [Symbol('DEFINITION'), 'LARGE'])
            return store.dump(value)

        def forbidden_printer(value):
            self.fail('Contact geometry must remain typed, without VL-PRIN1-TO-STRING')

        self.h.builtins.update({'EL:SIGNATURE': bounded_signature,
                               'VL-PRIN1-TO-STRING': forbidden_printer,
                               'EL:HASH': lambda value: self.fail('Short hashes cannot certify geometry')})
        rows = [Pair(f'D{i:03}', self.shape(geometry, f'D{i:03}', translation=float(i)))
                for i in range(18)]
        evidence = self.call('EL:DeviceContactEvidence', list(reversed(rows)))
        templates, instances = self.get('templates', evidence), self.get('instances', evidence)
        self.assertEqual(self.get('version', evidence), 3)
        self.assertEqual(len(templates), 1)
        self.assertEqual(len(instances), 18)
        template_geometry = self.call('CDR', templates[0])
        self.assertEqual(self.get('segments', template_geometry), segments)
        self.assertEqual(self.get('regions', template_geometry), [segments])
        self.assertEqual([row[0] for row in instances], [f'D{i:03}' for i in range(18)])
        self.assertEqual([row[2][0][4] for row in instances], [float(i) for i in range(18)])
        self.assertEqual(evidence, self.call('EL:DeviceContactEvidence', rows))

    def test_derived_contact_indexes_and_bounds_are_excluded(self):
        shape = self.shape(self.geometry())
        baseline = self.evidence(shape)
        for key in ('contact-tree', 'segment-bounds', 'contact-segment-bounds',
                    'contact-path-bounds', 'contact-regions', 'contact-holes',
                    'contact-template', 'contact-offset', 'contact-ready', 'bounds'):
            with self.subTest(field=key):
                changed = self.call('EL:Put', Symbol(key.upper()), ['different', key], shape)
                self.assertEqual(self.evidence(changed), baseline)

    def test_every_geometry_dependency_changes_exact_evidence(self):
        geometry = self.geometry()
        baseline = self.evidence(self.shape(geometry))
        changes = {
            'segments': [[[1.e-15, 0., 0.], [1., 0., 0.]]],
            'curves': [[[0., 0., 0.], .9999999999999999, 0., 6.283185307179586, None]],
            'regions': [[[[0., 0., 0.], [.9, 0., 0.]]]],
            'holes': [[[[.2, .2, 0.], [.4000000000000001, .2, 0.]]]],
            'issues': [[pair('code', Symbol('INVALID_GEOMETRY')), pair('object', 'A')]],
            'sampled-curves': True,
        }
        for key, value in changes.items():
            with self.subTest(field=key):
                changed = self.call('EL:Put', Symbol(key.upper()), value, copy.deepcopy(geometry))
                self.assertNotEqual(self.evidence(self.shape(changed)), baseline)

    def test_instance_transform_changes_without_definition_duplication(self):
        geometry = self.geometry()
        shape = self.shape(geometry)
        moved = self.shape(geometry, translation=1.e-15)
        baseline, changed = self.evidence(shape), self.evidence(moved)
        self.assertEqual(self.get('templates', baseline), self.get('templates', changed))
        self.assertNotEqual(self.get('instances', baseline), self.get('instances', changed))


class ContactEvidenceFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.f = fresh.FreshnessReuseTests()
        self.f.setUp()
        self.h = self.f.h
        self.h.builtins['EL:PERFREPORT'] = lambda summary: None
        self.call('EL:PerfStart', 'ELSTAT')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def metric(self, key):
        return self.call('EL:Get', key, self.h.lookup('*EL:PERFMETRICS*')) or 0

    def reset_operation(self):
        self.call('EL:PerfFinish', Symbol('FINISHED'))
        self.call('EL:PerfStart', 'ELSTAT')

    def test_failed_bounds_candidate_definition_edit_adds_contact_and_rejects_old_result(self):
        source = self.f.f
        source.block('SIGN', 'D', 'missed', [8., 3., 0.])
        source.bounds['missed'] = [[6., -1., 0.], [10., 4., 0.]]
        source.selected.append('missed')
        result = self.f.result()
        signature = self.get('device-contact-signature', self.get('snapshot', result))
        self.assertIn('missed', [row[0] for row in self.get('instances', signature)])
        self.assertNotIn('missed', [handle for circuit in self.get('circuits', result)
                                   for handle in self.get('devices', circuit) or []])
        original_bounds = copy.deepcopy(source.bounds['missed'])
        source.line('SIGN-edge-0', [-1., -3., 0.], [1., -3., 0.])
        self.assertEqual(source.bounds['missed'], original_bounds)
        self.reset_operation()
        self.assertFalse(truth(self.call('EL:FreshResult', result, source.cfg)))
        self.assertEqual(self.metric('network-proof-reuses'), 0)
        self.assertEqual(self.metric('network-build-calls'), 1)
        changed = self.f.result()
        self.assertIn('missed', [handle for circuit in self.get('circuits', changed)
                                for handle in self.get('devices', circuit) or []])

    def test_version_two_proof_forces_full_build_before_freshness_success(self):
        result = self.f.result()
        snapshot = self.get('snapshot', result)
        proof = self.get('network-proof', snapshot)
        self.assertEqual(self.get('version', proof), 3)
        old_proof = self.call('EL:Put', Symbol('VERSION'), 2, proof)
        old_proof = self.call('EL:Put', Symbol('CONTACTS'), [['legacy-full-shape']], old_proof)
        old_signature = copy.deepcopy(self.get('signature', snapshot))
        old_signature[1] = self.call('EL:Put', Symbol('NETWORK-PROOF'), old_proof, old_signature[1])
        old_snapshot = self.call('EL:Put', Symbol('NETWORK-PROOF'), old_proof, snapshot)
        old_snapshot = self.call('EL:Put', Symbol('SIGNATURE'), old_signature, old_snapshot)
        old_result = self.call('EL:Put', Symbol('SNAPSHOT'), old_snapshot, result)
        self.reset_operation()
        self.assertTrue(truth(self.call('EL:FreshResult', old_result, self.f.f.cfg)))
        self.assertEqual(self.metric('network-proof-reuses'), 0)
        self.assertEqual(self.metric('network-build-calls'), 1)
        upgraded = self.call('EL:PersistSourceSignature', old_result, self.f.f.cfg)
        self.assertEqual(self.get('version', self.get('network-proof', upgraded[1])), 3)


if __name__ == '__main__':
    unittest.main()
