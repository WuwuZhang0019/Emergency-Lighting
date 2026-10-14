"""Analytic device geometry. Date: 2026-10-13; synthetic CAD, not native acceptance."""
import math
import unittest
from autolisp_host import Pair, Symbol, truth
import test_contact_reuse as reuse


class AnalyticCurveTests(unittest.TestCase):
    def setUp(self):
        reuse.ContactReuseTests.setUp(self)
        # Date: 2026-10-14. Preserve strict analytic tests; drafting tolerance is tested separately.
        self.cfg = self.call('EL:Put', Symbol('PARAMS'), self.call('EL:Put', Symbol('EPS_DEVICE'), 0., self.get('params', self.cfg)), self.cfg)
        self.h.builtins['EQ'] = lambda a,b: a is b
        self.h.builtins['HANDENT'] = lambda value: value
    call = reuse.ContactReuseTests.call
    get = reuse.ContactReuseTests.get
    block = reuse.ContactReuseTests.block
    line = reuse.ContactReuseTests.line
    count = reuse.ContactReuseTests.count
    batch = reuse.ContactReuseTests.batch

    def circular(self, name='ROUND', handle='a', pos=(0., 0., 0.), arc=None, hole=False):
        self.block(name, 'D', handle, list(pos))
        edge = name+'-edge-0'
        self.entities[edge] = [Pair(0, 'ARC' if arc else 'CIRCLE'), Pair(5, edge),
            Pair(8, 'EL_HOLE' if hole else '0'), Pair(10, [0., 0., 0.]), Pair(40, 1.)]
        if arc:
            self.entities[edge] += [Pair(50, arc[0]), Pair(51, arc[1])]
        self.next_entity[edge] = name+'-end'
        return handle

    def shape(self, handle='a'):
        return self.batch([handle], True)[0]

    def point(self, p, shape):
        return truth(self.call('EL:ContourPointHit', p, shape, self.call('EL:StrictDeviceConfig', self.cfg)))

    def path(self, a, b, shape):
        return truth(self.call('EL:ContourPathHit', [Pair(Symbol('SEGMENTS'), [[a,b]])], shape,
                               self.call('EL:StrictDeviceConfig', self.cfg)))

    def test_circle_no_sampling_and_exact_points_paths(self):
        self.circular()
        self.h.builtins['EL:ARCPOINTS'] = lambda *a: self.fail('circle must not be sampled')
        shape = self.shape()
        self.assertFalse(self.get('segments', shape))
        self.assertEqual(len(self.get('curves', shape)), 1)
        for p, hit in (([0.,0.,0.],True), ([1.,0.,0.],True),
                       ([1.00001,0.,0.],False), ([0.,0.,0.01],False)):
            self.assertEqual(self.point(p, shape), hit)
        for a,b,hit in (([-2.,1.,0.],[2.,1.,0.],True),
                        ([-2.,1.00001,0.],[2.,1.00001,0.],False),
                        ([-2.,0.,0.],[2.,0.,0.],True),
                        ([-2.,0.,1.],[2.,0.,1.],False),
                        ([1.,0.,0.],[1.,0.,0.],True)):
            self.assertEqual(self.path(a,b,shape),hit)

    def test_arc_crossing_zero_has_no_disk_interior(self):
        self.circular(arc=(math.pi*1.5, math.pi*.5))
        self.h.builtins['EL:ARCPOINTS'] = lambda *a: self.fail('open arc must not be sampled')
        shape = self.shape()
        self.assertTrue(self.point([1.,0.,0.],shape))
        self.assertFalse(self.point([-1.,0.,0.],shape))
        self.assertFalse(self.point([0.,0.,0.],shape))
        self.assertTrue(self.path([0.,0.,0.],[2.,0.,0.],shape))
        self.assertFalse(self.path([-2.,-.5,0.],[-2.,.5,0.],shape))
        self.assertFalse(self.path([-1.,-2.,0.],[-1.,2.,0.],shape))

    def test_mirror_rotation_scale_and_translation_cache(self):
        self.circular(arc=(0.,math.pi/2))
        self.entities['a'] += [Pair(41,-2.),Pair(42,2.),Pair(50,math.pi/2)]
        shape = self.shape()
        self.assertTrue(self.point([-2.,0.,0.],shape))
        self.assertTrue(self.point([0.,-2.,0.],shape))
        self.assertFalse(self.point([2.,0.,0.],shape))
        self.circular(handle='b',pos=(20.,3.,5.),arc=(0.,math.pi/2))
        self.entities['b'] += [Pair(41,-2.),Pair(42,2.),Pair(50,math.pi/2)]
        calls = self.count('EL:DeviceDefinitionContour')
        shapes = self.batch(['a','b'],True)
        self.assertEqual(len(calls),1)
        self.assertTrue(self.point([18.,3.,5.],shapes[1]))
        self.assertFalse(self.point([18.,3.,0.],shapes[1]))
        self.assertTrue(self.path([17.,3.,5.],[19.,3.,5.],shapes[1]))

    def test_nonuniform_scale_falls_back_to_ellipse_segments(self):
        self.circular()
        self.entities['a'] += [Pair(41,2.)]
        sampled = self.count('EL:ArcPoints')
        shape = self.shape()
        self.assertEqual(len(sampled),1)
        self.assertFalse(self.get('curves',shape))
        self.assertTrue(self.get('segments',shape))
        self.assertTrue(self.point([2.,0.,0.],shape))
        self.assertFalse(self.point([0.,2.,0.],shape))

    def test_closed_arc_line_region_uses_existing_fallback(self):
        self.circular(arc=(0.,math.pi))
        self.line('diameter',[-1.,0.,0.],[1.,0.,0.])
        self.next_entity['ROUND-edge-0']='diameter'
        self.next_entity['diameter']='ROUND-end'
        shape=self.shape()
        self.assertFalse(self.get('curves',shape))
        self.assertTrue(self.point([0.,.5,0.],shape))
        self.assertFalse(self.point([0.,-.5,0.],shape))

    def test_circle_hole_subtracts_from_polygon_region(self):
        self.block('BOX','D','a',[0.,0.,0.])
        self.entities['hole']=[Pair(0,'CIRCLE'),Pair(5,'hole'),Pair(8,'EL_HOLE'),
                               Pair(10,[0.,0.,0.]),Pair(40,.5)]
        self.next_entity['BOX-edge-3']='hole';self.next_entity['hole']='BOX-end'
        shape=self.shape()
        self.assertFalse(self.point([0.,0.,0.],shape))
        self.assertTrue(self.point([.75,0.,0.],shape))
        self.assertTrue(self.point([.5,0.,0.],shape))

    def test_polygon_hole_subtracts_from_circle_region(self):
        self.circular()
        self.entities['hole']=[Pair(0,'LWPOLYLINE'),Pair(5,'hole'),Pair(8,'EL_HOLE'),Pair(70,1),
            Pair(10,[-.2,-.2]),Pair(10,[.2,-.2]),Pair(10,[.2,.2]),Pair(10,[-.2,.2])]
        self.next_entity['ROUND-edge-0']='hole';self.next_entity['hole']='ROUND-end'
        shape=self.shape()
        self.assertFalse(self.point([0.,0.,0.],shape))
        self.assertTrue(self.point([.75,0.,0.],shape))

    def test_circle_circle_and_arc_contact(self):
        circle=[[0.,0.,0.],1.,0.,math.tau,None]
        for center,r,hit in (([2.,0.,0.],1.,True),([2.00001,0.,0.],1.,False),
                              ([0.,0.,0.],.5,False),([0.,0.,0.],1.,True),
                              ([0.,0.,.01],1.,False),([.5,0.,0.],.5,True)):
            self.assertEqual(truth(self.call('EL:CurvesTouch',circle,[center,r,0.,math.tau,None])),hit)
        right=[[0.,0.,0.],1.,-math.pi/2,math.pi,None]
        left=[[0.,0.,0.],1.,math.pi*.75,math.pi*.5,None]
        self.assertFalse(truth(self.call('EL:CurvesTouch',right,left)))
        self.assertFalse(truth(self.call('EL:CurvesTouch',right,[[-2.,0.,0.],1.,0.,math.tau,None])))

    def test_device_to_device_including_line_circle(self):
        self.circular(handle='a')
        self.circular(name='OTHER',handle='b',pos=(2.,0.,0.))
        a=[Pair(Symbol('ID'),'a')]; b=[Pair(Symbol('ID'),'b')]
        self.assertTrue(truth(self.call('EL:DevicesTouch',a,b)))
        self.h.frames[0]['*EL:DEVICECONTACTCACHE*']=None
        self.block('SQUARE','D','c',[2.,0.,0.])
        c=[Pair(Symbol('ID'),'c')]
        self.assertTrue(truth(self.call('EL:DevicesTouch',a,c)))
        self.assertTrue(truth(self.call('EL:DevicesTouch',c,a)))

    def test_nested_circle_keeps_one_primitive(self):
        self.circular(name='CHILD',handle='inner',pos=(3.,0.,0.))
        self.block('OUTER','D','a',[10.,0.,0.])
        self.entities['inner'] += [Pair(41,2.),Pair(42,2.)]
        self.blocks['OUTER'][-1] = Pair(-2,'inner')
        self.next_entity['inner']='OUTER-end'
        self.h.builtins['EL:ARCPOINTS']=lambda *a: self.fail('nested circle sampled')
        shape=self.shape()
        self.assertEqual(len(self.get('curves',shape)),1)
        self.assertTrue(self.point([15.,0.,0.],shape))
        self.assertFalse(self.point([15.01,0.,0.],shape))

    def test_negative_ocs_normal_reverses_arc(self):
        self.circular(arc=(0.,math.pi/2))
        self.entities['ROUND-edge-0'].append(Pair(210,[0.,0.,-1.]))
        self.h.builtins['TRANS']=lambda p,normal,*args: [-p[0],p[1],-p[2]] if normal==[0.,0.,-1.] else p
        shape=self.shape()
        self.assertTrue(self.point([-1.,0.,0.],shape))
        self.assertTrue(self.point([0.,1.,0.],shape))
        self.assertFalse(self.point([1.,0.,0.],shape))

    def test_network_reaches_circle_at_unsampled_tangent(self):
        self.block('BOX','P','panel',[-3.,1.,0.])
        self.circular()
        self.line('wire',[-2.,1.,0.],[2.,1.,0.],'W')
        self.selected=['panel','a','wire']
        self.h.builtins['EL:ARCPOINTS']=lambda *a: self.fail('network circle sampled')
        snapshot=self.call('EL:SimpleCollect',self.cfg)
        result=self.call('EL:SimpleNetwork',snapshot,self.cfg,'panel')
        self.assertEqual([self.get('id',b) for b in self.get('devices',result)],['a'])
        self.assertTrue(self.get('device-contact-signature',self.get('snapshot',result)))

    def test_circle_and_two_lines_avoid_thousands_of_segments(self):
        self.circular()
        self.entities['ROUND-edge-0'][-1]=Pair(40,100.)
        self.line('cross1',[-110.,0.,0.],[110.,0.,0.])
        self.line('cross2',[0.,-110.,0.],[0.,110.,0.])
        self.next_entity['ROUND-edge-0']='cross1'
        self.next_entity['cross1']='cross2';self.next_entity['cross2']='ROUND-end'
        self.h.builtins['EL:ARCPOINTS']=lambda *a: self.fail('dense circle sampled')
        shape=self.shape()
        self.assertEqual(len(self.get('segments',shape)),2)
        self.assertEqual(len(self.get('curves',shape)),1)
        angle=.12345
        self.assertTrue(self.point([100.*math.cos(angle),100.*math.sin(angle),0.],shape))

    def test_hidden_circle_is_not_read(self):
        self.circular()
        self.entities['ROUND-edge-0'].append(Pair(60,1))
        shape=self.shape()
        self.assertFalse(self.get('curves',shape))
        self.assertFalse(self.point([0.,0.,0.],shape))

    def semicircle_polyline(self, name='ROUND', handle='a', hole=False, bulges=(1.,1.)):
        self.circular(name=name, handle=handle)
        edge = name+'-edge-0'
        self.entities[edge] = [Pair(0, 'LWPOLYLINE'), Pair(5, edge),
            Pair(8, 'EL_HOLE' if hole else '0'), Pair(70, 1), Pair(38, 0.),
            Pair(10, [-100.,0.]), Pair(42, bulges[0]),
            Pair(10, [100.,0.]), Pair(42, bulges[1])]
        return handle

    def test_two_bulge_semicircles_use_one_exact_circle(self):
        self.semicircle_polyline()
        self.h.builtins['EL:ARCPOINTS'] = lambda *a: self.fail('closed two-bulge circle sampled')
        shape = self.call('EL:DeviceContour', 'a')
        self.assertFalse(self.get('segments', shape))
        self.assertFalse(self.get('sampled-curves', shape))
        self.assertEqual(len(self.get('curves', shape)), 1)
        angle = .12345
        self.assertTrue(self.point([100.*math.cos(angle),100.*math.sin(angle),0.],shape))
        self.assertTrue(self.point([0.,0.,0.],shape))
        self.assertFalse(self.point([100.00001,0.,0.],shape))
        self.assertTrue(self.path([-200.,100.,0.],[200.,100.,0.],shape))
        self.assertFalse(self.path([-200.,100.00001,0.],[200.,100.00001,0.],shape))

    def test_bulge_circle_hole_and_negative_ocs_keep_exact_contact(self):
        self.circular()
        self.semicircle_polyline(name='HOLE',handle='hole-instance',hole=True,bulges=(-1.,-1.))
        self.entities['ROUND-edge-0'][-1] = Pair(40, 200.)
        hole = 'HOLE-edge-0'
        self.entities[hole].append(Pair(210,[0.,0.,-1.]))
        self.h.builtins['TRANS'] = lambda p,normal,*a: [-p[0],p[1],-p[2]] if normal==[0.,0.,-1.] else p
        self.next_entity['ROUND-edge-0']=hole; self.next_entity[hole]='ROUND-end'
        self.h.builtins['EL:ARCPOINTS'] = lambda *a: self.fail('bulge circle hole sampled')
        shape = self.call('EL:DeviceContour', 'a')
        self.assertEqual(len(self.get('curves', shape)), 2)
        self.assertFalse(self.point([0.,0.,0.],shape))
        self.assertTrue(self.point([100.,0.,0.],shape))
        self.assertTrue(self.point([150.,0.,0.],shape))
        self.assertFalse(self.point([150.,0.,.01],shape))

    def test_nonuniform_bulge_circle_retains_sampled_ellipse_fallback(self):
        self.semicircle_polyline()
        self.entities['a'] += [Pair(41,2.)]
        sampled = self.count('EL:ArcPoints')
        shape = self.call('EL:DeviceContour', 'a')
        self.assertEqual(len(sampled),2)
        self.assertTrue(self.get('sampled-curves',shape))
        self.assertFalse(self.get('curves',shape))
        self.assertTrue(self.point([200.,0.,0.],shape))
        self.assertFalse(self.point([0.,200.,0.],shape))

    def test_other_closed_bulge_shapes_keep_existing_sampling(self):
        sampled = self.count('EL:ArcPoints')
        for bulges in ((1.,-1.),(1.+1.0e-13,1.+1.0e-13)):
            with self.subTest(bulges=bulges):
                self.semicircle_polyline(bulges=bulges)
                sampled.clear()
                shape = self.call('EL:DeviceContour','a')
                self.assertEqual(len(sampled),2)
                self.assertTrue(self.get('sampled-curves',shape))
                self.assertFalse(self.get('curves',shape))

    def test_definition_shape_maps_root_base_rotation_scale_and_mirror(self):
        self.semicircle_polyline()
        self.blocks['ROUND'][1] = Pair(10,[7.,3.,2.])
        self.entities['a'] += [Pair(41,-2.),Pair(42,2.),Pair(43,3.),Pair(50,math.pi/2)]
        self.entities['a'][4] = Pair(10,[50.,30.,8.])
        local = self.call('EL:DeviceDefinitionContour','a')
        self.assertEqual(self.get('curves',local)[0][0],[0.,0.,0.])
        matrix = self.call('EL:InsertMatrix','a')
        mapped = self.call('EL:TransformShape',local,matrix)
        direct = self.call('EL:DeviceContour','a')
        center = self.call('EL:AffinePoint',[0.,0.,0.],matrix)
        for point in (center, self.call('EL:AffinePoint',[100.,0.,0.],matrix),
                      self.call('EL:AffinePoint',[100.00001,0.,0.],matrix)):
            self.assertEqual(self.point(point,mapped),self.point(point,direct))
        self.assertTrue(self.point(center,mapped))
        self.assertFalse(self.point([center[0]+200.00001,center[1],center[2]],mapped))
        self.assertIsNone(self.call('EL:TransformShape',local,[2.,0.,0.,1.,0.,0.,0.,1.]))

    def test_definition_shape_preserves_nested_pose_and_exact_polygon_holes(self):
        self.circular(name='CHILD',handle='inner',pos=(3.,0.,0.))
        self.block('OUTER','D','a',[10.,0.,0.])
        self.blocks['CHILD'][1] = Pair(10,[.5,0.,0.])
        self.entities['inner'] += [Pair(41,2.),Pair(42,2.),Pair(50,math.pi/2)]
        self.blocks['OUTER'][-1] = Pair(-2,'inner')
        self.next_entity['inner'] = 'OUTER-end'
        local = self.call('EL:DeviceDefinitionContour','a')
        mapped = self.call('EL:TransformShape',local,self.call('EL:InsertMatrix','a'))
        self.assertTrue(self.point([13.,1.,0.],mapped))
        self.assertFalse(self.point([13.,1.00001,0.],mapped))
        ring = [[[-.5,-.5,0.],[.5,-.5,0.]],[[.5,-.5,0.],[.5,.5,0.]],
                [[.5,.5,0.],[-.5,.5,0.]],[[-.5,.5,0.],[-.5,-.5,0.]]]
        local = self.call('EL:Put',Symbol('HOLES'),[ring],local)
        matrix = [0.,2.,-2.,0.,10.,20.,5.,1.]
        mapped = self.call('EL:TransformShape',local,matrix)
        self.assertEqual(self.get('holes',mapped),
                         [self.call('EL:TransformSegments',ring,matrix)])

    def test_sampled_definition_keeps_instance_fallback(self):
        self.circular(arc=(0.,math.pi))
        self.line('diameter',[-1.,0.,0.],[1.,0.,0.])
        self.next_entity['ROUND-edge-0']='diameter';self.next_entity['diameter']='ROUND-end'
        local = self.call('EL:DeviceDefinitionContour','a')
        self.assertTrue(self.get('sampled-curves',local))
        self.assertIsNone(self.call('EL:TransformShape',local,[2.,0.,0.,2.,0.,0.,0.,1.]))
        self.assertIsNone(self.call('EL:TransformShape',local,[0.,-1.,1.,0.,20.,3.,4.,1.]))

    def test_nested_nonuniform_scales_can_cancel_into_an_exact_wcs_circle(self):
        self.circular(name='CHILD',handle='inner')
        self.entities['inner'] += [Pair(41,2.)]
        self.block('OUTER','D','a',[0.,0.,0.])
        self.blocks['OUTER'][-1]=Pair(-2,'inner');self.next_entity['inner']='OUTER-end'
        self.entities['a'] += [Pair(41,.5)]
        local=self.call('EL:DeviceDefinitionContour','a')
        self.assertTrue(self.get('sampled-curves',local))
        self.assertIsNone(self.call('EL:TransformShape',local,self.call('EL:InsertMatrix','a')))
        angle=.12345;point=[math.cos(angle),math.sin(angle),0.]
        direct=self.batch(['a'],None)[0]
        cached=self.batch(['a'],True)[0]
        self.assertEqual(len(self.get('curves',cached)),1)
        self.assertTrue(self.point(point,direct))
        self.assertTrue(self.point(point,cached))
        self.assertTrue(self.path([-2.,1.,0.],[2.,1.,0.],cached))
        self.assertFalse(self.path([-2.,1.00001,0.],[2.,1.00001,0.],cached))

    def test_wcs_region_closure_matches_direct_after_scale_opens_or_closes_gap(self):
        for scale,gap,hit in ((1e6,5e-8,False),(.1,5e-7,True)):
            with self.subTest(scale=scale,gap=gap):
                self.block('BOX','D','a',[0.,0.,0.])
                self.entities['BOX-edge-3'][-3]=Pair(11,[-1.,-1.+gap,0.])
                self.entities['a'] += [Pair(41,scale),Pair(42,scale)]
                direct=self.batch(['a'],None)[0]
                cached=self.batch(['a'],True)[0]
                self.assertEqual(self.point([0.,0.,0.],direct),hit)
                self.assertEqual(self.point([0.,0.,0.],cached),hit)

    def test_wcs_hole_closure_retains_open_paths_and_matches_direct_pose(self):
        for scale,gap,hit in ((1e6,5e-8,True),(.1,5e-7,False)):
            with self.subTest(scale=scale,gap=gap):
                self.block('BOX','D','a',[0.,0.,0.])
                self.entities['hole']=[Pair(0,'LWPOLYLINE'),Pair(5,'hole'),Pair(8,'EL_HOLE'),Pair(70,0),
                    Pair(10,[-.5,-.5]),Pair(10,[.5,-.5]),Pair(10,[.5,.5]),Pair(10,[-.5,.5]),
                    Pair(10,[-.5,-.5+gap])]
                self.next_entity['BOX-edge-3']='hole';self.next_entity['hole']='BOX-end'
                self.entities['a'] += [Pair(41,scale),Pair(42,scale)]
                local=self.call('EL:DeviceDefinitionContour','a')
                self.assertEqual(len(self.get('hole-paths',local)),1)
                mapped=self.call('EL:TransformShape',local,self.call('EL:InsertMatrix','a'))
                self.assertEqual(bool(self.get('holes',mapped)),not hit)
                direct=self.batch(['a'],None)[0]
                cached=self.batch(['a'],True)[0]
                self.assertEqual(self.point([0.,0.,0.],direct),hit)
                self.assertEqual(self.point([0.,0.,0.],cached),hit)

    def test_definition_rejects_xrefs_recursion_and_tilted_root_plane(self):
        self.circular()
        self.blocks['ROUND'][2] = Pair(70,4)
        local=self.call('EL:DeviceDefinitionContour','a')
        self.assertIn(Symbol('UNSUPPORTED_BLOCK'),[self.get('code',i) for i in self.get('issues',local)])
        self.blocks['ROUND'][2] = Pair(70,0)
        self.blocks['ROUND'][-1] = Pair(-2,'a');self.next_entity['a']='ROUND-end'
        local=self.call('EL:DeviceDefinitionContour','a')
        self.assertIn(Symbol('RECURSIVE_BLOCK'),[self.get('code',i) for i in self.get('issues',local)])
        self.entities['a'].append(Pair(210,[1.,0.,0.]))
        self.h.builtins['TRANS']=lambda p,n,*a: [p[2],p[1],-p[0]] if n==[1.,0.,0.] else p
        local=self.call('EL:DeviceDefinitionContour','a')
        self.assertFalse(self.get('curves',local))
        self.assertIn(Symbol('UNSUPPORTED_BLOCK'),[self.get('code',i) for i in self.get('issues',local)])


if __name__ == '__main__':
    unittest.main()
