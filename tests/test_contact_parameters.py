"""Independent device contact settings. Date: 2026-10-14; finite adapter only."""
import unittest
from autolisp_host import Host, Symbol, truth
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ContactParameterTests(unittest.TestCase):
    def setUp(self):
        self.h=Host()
        for module in ('common','config','geometry','simple','diagram-update'):
            self.h.load_definitions(ROOT/'src'/f'{module}.lsp')
        self.params=self.call('EL:SuggestedParams')
        self.cfg=self.put('params',self.params,self.call('EL:DefaultConfig','parameters.dwg'))
    def call(self,name,*args):return self.h.call(Symbol(name.upper()),list(args))
    def get(self,key,record):return self.call('EL:Get',Symbol(key.upper()),record)
    def put(self,key,value,record):return self.call('EL:Put',Symbol(key.upper()),value,record)
    def test_default_and_legacy_config_preserve_gap_rules(self):
        self.assertEqual(self.get('eps_device',self.params),.01)
        legacy=[r for r in self.params if self.call('CAR',r)!=Symbol('EPS_DEVICE')]
        self.assertTrue(truth(self.call('EL:ParamsValid',legacy)))
        self.assertEqual(self.call('EL:DeviceContactTolerance',self.put('params',legacy,self.cfg)),.01)
        upgraded=self.call('EL:GapParams',legacy)
        self.assertEqual(self.get('eps_device',upgraded),.01)
        for key in ('eps_touch','eps_boundary','Dmax','eps_perp','eps_z','theta_max'):
            self.assertEqual(self.get(key,upgraded),self.get(key,self.params))
    def test_explicit_zero_is_strict_and_invalid_values_are_rejected(self):
        p=self.put('eps_device',0.,self.params)
        self.assertTrue(truth(self.call('EL:ParamsValid',p)))
        self.assertEqual(self.call('EL:DeviceContactTolerance',self.put('params',p,self.cfg)),1.e-7)
        self.assertEqual(self.get('eps_device',self.call('EL:GapParams',p)),0.)
        for value in (-.01,'0.01',None):
            self.assertFalse(truth(self.call('EL:ParamsValid',self.put('eps_device',value,self.params))))
    def test_parameter_prompt_preserves_other_values(self):
        values=iter((None,None,.02,None));prompts=[]
        self.h.builtins['GETREAL']=lambda prompt:prompts.append(prompt) or next(values)
        edited=self.call('EL:InputParamValues',self.params)
        self.assertEqual(len(prompts),4)
        self.assertIn('设备真实轮廓接触容差',prompts[2])
        self.assertEqual(self.get('eps_device',edited),.02)
        for key in ('eps_touch','eps_boundary','Dmax','eps_z'):
            self.assertEqual(self.get(key,edited),self.get(key,self.params))
    def test_tolerance_change_invalidates_recognition_rules(self):
        changed=self.put('params',self.put('eps_device',.02,self.params),self.cfg)
        self.assertNotEqual(self.call('EL:RecognitionRules',self.cfg),self.call('EL:RecognitionRules',changed))
        self.assertFalse(truth(self.call('EL:SameParams',self.params,self.get('params',changed))))
    def test_fixed_stat_keeps_saved_device_tolerance_and_default_gap_policy(self):
        saved=self.put('params',self.put('Dmax',9999.,self.put('eps_device',.025,self.params)),self.cfg)
        actual=self.call('EL:FixedRecognitionParams',saved)
        self.assertEqual(self.get('eps_device',actual),.025)
        self.assertEqual(self.get('Dmax',actual),2000.)
        strict=self.call('EL:FixedRecognitionParams',self.put('params',self.put('eps_device',0.,self.params),self.cfg))
        self.assertEqual(self.get('eps_device',strict),0.)
    def test_current_drawing_tolerance_overrides_old_system_config(self):
        saved=self.put('params',self.put('eps_device',.025,self.params),self.cfg)
        self.h.frames[0]['*EL:ROOT*']='fixture/'
        self.h.builtins.update({'EL:CONFIGPATH':lambda drawing:'cfg.eld','FINDFILE':lambda path:path,
                               'EL:READDATA':lambda path:saved})
        current=self.call('EL:CurrentJunctionConfig',self.cfg)
        self.assertEqual(self.get('eps_device',self.get('params',current)),.025)
        self.assertNotEqual(self.call('EL:RecognitionRules',self.cfg),self.call('EL:RecognitionRules',current))
    def test_actual_start_pick_passes_saved_tolerance_to_recognition_and_panel(self):
        from test_circuit_starts import CircuitStartTests
        f=CircuitStartTests();f.setUp()
        saved=f.call('EL:Put',Symbol('PARAMS'),f.call('EL:Put',Symbol('EPS_DEVICE'),.025,f.get('params',f.cfg)),f.cfg)
        f.h.builtins['EL:LOADCONFIG']=lambda:saved
        f.call('EL:RememberStartPanel','panel','箱一')
        f.picks([['w1',[1.,0.,0.]],None])
        f.call('EL:FixedStartPick')
        self.assertEqual(len(f.opened),1)
        result,cfg=f.opened[0]
        self.assertEqual(f.get('eps_device',f.get('params',cfg)),.025)
        self.assertEqual(f.devices(result),[['a','b']])
if __name__=='__main__':unittest.main()
