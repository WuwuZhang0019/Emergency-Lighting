"""Source and adapter contracts. These checks do not run AutoCAD or DCL."""
import pathlib
import re
import tempfile
import unittest

from autolisp_host import Host, Symbol, parse, seq, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


def expressions(node):
    if not isinstance(node, list) or not node:
        return
    if node[0] == Symbol('QUOTE'):
        body = node[1]
        if isinstance(body, list) and body[0] == Symbol('LAMBDA'):
            for form in body[2:]:
                yield from expressions(form)
        return
    yield node
    for child in node:
        yield from expressions(child)


class SourceContracts(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.defs = {}
        for path in (ROOT/'src').glob('*.lsp'):
            self.h.load_definitions(path)
            for form in parse(path.read_text()):
                if isinstance(form,list) and form[0] == Symbol('DEFUN'):
                    self.defs[str(form[1])] = form

    def test_forms_arities_and_local_assignments(self):
        for name, form in self.defs.items():
            locals_ = set(seq(form[2]))
            for body in form[3:]:
                for expr in expressions(body):
                    op = expr[0]
                    if not isinstance(op, Symbol):
                        continue
                    with self.subTest(function=name, operation=str(op)):
                        if op == 'SETQ':
                            self.assertEqual(len(expr)%2,1)
                            for var in expr[1::2]:
                                self.assertIsInstance(var,Symbol)
                                self.assertTrue(var in locals_ or str(var).startswith('*'),var)
                        if op == 'IF': self.assertIn(len(expr),[3,4])
                        if op in self.defs:
                            params = seq(self.defs[op][2])
                            arity = params.index(Symbol('/')) if Symbol('/') in params else len(params)
                            self.assertEqual(len(expr)-1,arity)
                        elif op.startswith('EL:'):
                            self.fail(f'undefined internal function: {op}')

    def test_geometry_and_topology_do_not_mutate_drawing(self):
        forbidden={'ENTMOD','ENTMAKE','ENTMAKEX','ENTDEL','COMMAND','COMMAND-S','SETVAR'}
        for filename in ['geometry.lsp','topology.lsp','simple.lsp']:
            for form in parse((ROOT/'src'/filename).read_text()):
                for expr in expressions(form):
                    if isinstance(expr[0],Symbol):
                        self.assertNotIn(str(expr[0]),forbidden)
                        self.assertFalse(str(expr[0]).startswith('VLA-PUT-'))

    def test_dcl_keys_and_callback_syntax(self):
        ui = (ROOT/'ui/power.dcl').read_text()
        keys=set(re.findall(r'key\s*=\s*"([^"]+)"',ui)) | {'accept','cancel'}
        code='\n'.join((ROOT/'src'/name).read_text() for name in ('main.lsp','simple.lsp','panel.lsp'))
        used=set(re.findall(r'\((?:action_tile|set_tile|get_tile|start_list)\s+"([^"]+)"',code))
        self.assertTrue(used <= keys, used-keys)
        for form in parse(code):
            for expr in expressions(form):
                if expr[0] == Symbol('ACTION_TILE'):
                    if isinstance(expr[2], str):
                        self.assertTrue(parse(expr[2]))
                    else:
                        for index in range(4 if str(form[1]) == "EL:THUMBACTIONS" else 8):
                            self.h.frames[0]['KEY'] = str(index)
                            self.assertIn(self.h.evaluate(expr[1]), keys)
                            self.assertTrue(parse(self.h.evaluate(expr[2])))
        self.assertEqual(ui.count('{'),ui.count('}'))

    def test_atomic_config_write_restores_previous_file_on_failure(self):
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/'config.eld'
            path.write_text('previous-valid-data')
            def rename(src,dst):
                if src.endswith('.tmp'): return None
                pathlib.Path(src).rename(dst)
                return True
            self.h.builtins.update({
                'OPEN': lambda p,mode,*encoding: open(p,mode,encoding='utf-8'),
                'WRITE-LINE': lambda line,file:file.write(line+'\n'),
                'CLOSE': lambda file:file.close(),
                'FINDFILE': lambda p:p if pathlib.Path(p).is_file() else None,
                'VL-FILE-DELETE': lambda p:pathlib.Path(p).unlink() or True,
                'VL-FILE-RENAME': rename,
            })
            self.h.frames[0]['TEST:PATH']=str(path)
            self.assertFalse(truth(self.h.run('(EL:WriteData test:path \'((version . 1)))')))
            self.assertEqual(path.read_text(),'previous-valid-data')
            self.assertFalse(pathlib.Path(str(path)+'.tmp').exists())

    def test_rollback_only_deletes_created_objects_even_if_one_delete_fails(self):
        deleted=[]
        def delete(obj):
            deleted.append(obj)
            if obj=='already-deleted': raise RuntimeError('CAD deletion failure')
        self.h.builtins['VLA-DELETE']=delete
        self.h.run('(setq *EL:Created* \'("new-text" "already-deleted" "new-block")) (EL:RollbackCreated)')
        self.assertEqual(deleted,['new-text','already-deleted','new-block'])
        self.assertIsNone(self.h.lookup('*EL:CREATED*'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
