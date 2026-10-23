"""Serialized proof candidates still verify current source; Date: 2026-10-21."""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_freshness_reuse as fixture


def native_list_pairs(value):
    """Date: 2026-10-13. (10 . (x y z)) and (10 x y z) are one native list.

    The finite ENTGET fixture constructs Pair objects, whereas StableData/store
    readback produce proper lists. Normalize that representation at the fixture
    boundary; keep the host's exact EQUAL and every numeric value unchanged.
    """
    if isinstance(value, Pair):
        head, tail = native_list_pairs(value.car), native_list_pairs(value.cdr)
        return [head] + (tail or []) if tail is None or isinstance(tail, list) else Pair(head, tail)
    if isinstance(value, list):
        return [native_list_pairs(item) for item in value] or None
    return value


class NetworkProofTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.FreshnessReuseTests()
        self.f.setUp()
        self.h = self.f.h
        entget = self.h.builtins['ENTGET']
        self.h.builtins['ENTGET'] = lambda *args: native_list_pairs(entget(*args))
        self.call('EL:PerfStart', 'ELSTAT')
        self.result = self.f.result()
        self.call('EL:PerfFinish', Symbol('FINISHED'))
        self.call('EL:PerfStart', 'ELSTAT')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def metric(self, name):
        return self.call('EL:Get', name, self.h.lookup('*EL:PERFMETRICS*')) or 0

    def roundtripped(self, signature):
        saved = self.call('EL:StoreDecode', self.call('EL:StoreEncode', signature))
        # Date: 2026-10-21. The historical panel restore entry point was removed.
        # Exercise the real codec, snapshot constructor and freshness verifier
        # without inventing a production history flow or replacing its checks.
        snapshot = self.call('EL:CircuitSnapshot', saved[1], self.get('panel', self.result))
        return self.call('EL:Put', Symbol('SNAPSHOT'), snapshot, self.result)

    def test_roundtripped_candidate_recollects_and_checks_geometry_without_build(self):
        restored = self.roundtripped(self.get('signature', self.get('snapshot', self.result)))
        self.assertTrue(truth(restored))
        self.assertTrue(truth(self.call('EL:FreshResult', restored, self.f.f.cfg)))
        self.assertEqual(self.metric('network-build-calls'), 0)
        self.assertEqual(self.metric('network-proof-reuses'), 1)
        self.assertEqual(self.metric('source-collect-calls'), 1)
        self.assertGreater(self.metric('network-geometry-checks'), 0)

    def test_legacy_signature_builds_once_then_saves_reusable_candidate(self):
        signature = self.call('EL:SourceSignatureCore', self.get('signature', self.get('snapshot', self.result)))
        restored = self.roundtripped(signature)
        self.assertTrue(truth(self.call('EL:FreshResult', restored, self.f.f.cfg)))
        self.assertEqual(self.metric('network-build-calls'), 1)
        upgraded = self.call('EL:PersistSourceSignature', restored, self.f.f.cfg)
        self.assertNotEqual(upgraded, signature)
        self.call('EL:FreshBoundary')
        self.assertEqual(self.call('EL:PersistSourceSignature', restored, self.f.f.cfg), signature)
        self.call('EL:PerfFinish', Symbol('FINISHED'))
        self.call('EL:PerfStart', 'ELSTAT')
        self.assertTrue(truth(self.call('EL:FreshResult', self.roundtripped(upgraded), self.f.f.cfg)))
        self.assertEqual(self.metric('network-build-calls'), 0)

    def test_definition_edit_and_source_addition_rebuild_and_reject_stale(self):
        self.f.f.line('LAMP-edge-0', [-.5, -.5, 0.], [.5, -.5, 0.])
        self.assertFalse(truth(self.call('EL:FreshResult', self.result, self.f.f.cfg)))
        self.assertGreater(self.metric('network-build-calls'), 0)

    def test_added_source_invalidates_and_removal_allows_verified_reuse(self):
        self.f.f.line('new-wire', [200., 0., 0.], [210., 0., 0.], 'W')
        self.f.f.selected.append('new-wire')
        self.assertFalse(truth(self.call('EL:FreshResult', self.result, self.f.f.cfg)))
        self.assertEqual(self.metric('network-proof-reuses'), 0)
        self.f.f.selected.remove('new-wire')
        self.call('EL:FreshBoundary')
        self.assertTrue(truth(self.call('EL:FreshResult', self.result, self.f.f.cfg)))
        self.assertEqual(self.metric('network-proof-reuses'), 1)

    def test_unknown_rule_change_and_explicit_disable_force_original_build(self):
        cfg = self.call('EL:Put', Symbol('FUTURE-RULE'), 7, self.f.f.cfg)
        self.call('EL:FreshResult', self.result, cfg)
        self.assertEqual(self.metric('network-proof-reuses'), 0)
        self.assertEqual(self.metric('network-build-calls'), 1)
        self.call('EL:FreshBoundary')
        self.h.frames[0]['*EL:NETWORKREUSEDISABLED*'] = True
        self.call('EL:FreshResult', self.result, self.f.f.cfg)
        self.assertEqual(self.metric('network-build-calls'), 2)

if __name__ == '__main__': unittest.main()
