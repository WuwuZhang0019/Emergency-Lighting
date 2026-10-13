"""Small test host for pure AutoLISP functions; deliberately not a CAD emulator.

Loads the actual .lsp sources. CAD APIs fail if called. NIL, dynamic scope,
integer division and AutoLISP LAST (one-element list) are modelled explicitly.
Date: 2026-10-12.
"""
import math
import re
from functools import cmp_to_key
from dataclasses import dataclass


class Symbol(str):
    pass


@dataclass(frozen=True)
class Pair:
    car: object
    cdr: object


@dataclass
class CaughtError:
    exception: Exception


def tokens(text):
    return re.findall(r';[^\n]*|"(?:\\.|[^"\\])*"|[()]|\'|[^\s()\';]+', text)


def parse(text):
    ts = [t for t in tokens(text) if not t.startswith(';')]
    i = 0

    def one():
        nonlocal i
        if i >= len(ts):
            raise SyntaxError('unexpected EOF')
        t = ts[i]
        i += 1
        if t == '(':
            out = []
            while i < len(ts) and ts[i] != ')':
                if ts[i] == '.':
                    i += 1
                    tail = one()
                    if i >= len(ts) or ts[i] != ')':
                        raise SyntaxError('bad dotted pair')
                    i += 1
                    for value in reversed(out):
                        tail = Pair(value, tail)
                    return tail
                out.append(one())
            if i >= len(ts):
                raise SyntaxError('unclosed list')
            i += 1
            return out or None
        if t == ')':
            raise SyntaxError('unexpected )')
        if t == "'":
            return [Symbol('QUOTE'), one()]
        if t.startswith('"'):
            return re.sub(r'\\([0-7]{3}|.)', lambda m: chr(int(m[1], 8)) if len(m[1]) == 3
                          else {'e': '\x1b', 'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), t[1:-1])
        try:
            return float(t) if any(x in t.lower() for x in ['.', 'e']) else int(t)
        except ValueError:
            return Symbol(t.upper())

    out = []
    while i < len(ts):
        out.append(one())
    return out


def seq(x):
    return [] if x is None else x


def car(x):
    return x.car if isinstance(x, Pair) else (x[0] if x else None)


def cdr(x):
    return x.cdr if isinstance(x, Pair) else (x[1:] or None if x else None)


def cons(a, b):
    return [a] + seq(b) if b is None or isinstance(b, list) else Pair(a, b)


def entity_data(data, apps=None):
    """Date: 2026-10-11. Match native entget application selection, including '*'."""
    if data is None:
        return None
    basic = [row for row in data if car(row) != -3]
    if not apps:
        return basic
    wanted = {name.upper() for name in apps}
    for row in data:
        if car(row) != -3:
            continue
        selected = [app for app in seq(cdr(row))
                    if '*' in wanted or str(car(app)).upper() in wanted]
        if selected:
            basic.append([-3, *selected])
    return basic


def truth(x):
    return x is not None and x is not False and x != []


def equal(a, b, fuzz=None):
    if isinstance(a, Symbol) != isinstance(b, Symbol): return False
    if isinstance(a, bool) != isinstance(b, bool): return False
    if fuzz is not None and isinstance(a, (float, int)) and isinstance(b, (float, int)):
        return abs(a - b) <= fuzz
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y, fuzz) for x, y in zip(a, b))
    return a == b


def quoted(x):
    if isinstance(x, Symbol) and x == 'NIL': return None
    if isinstance(x, Symbol) and x == 'T': return True
    if isinstance(x, Pair): return Pair(quoted(x.car), quoted(x.cdr))
    if isinstance(x, list): return [quoted(v) for v in x] or None
    return x


def lisp_type(x):
    if x is None or x is False: return None
    if isinstance(x, Symbol): return Symbol('SYM')
    if isinstance(x, str): return Symbol('STR')
    if isinstance(x, int): return Symbol('INT')
    if isinstance(x, float): return Symbol('REAL')
    return Symbol('LIST')


class Host:
    def __init__(self, step_limit=10000000):
        self.frames = [{'NIL': None, 'T': True, 'PI': math.pi}]
        self.functions = {}
        self.steps = 0
        self.step_limit = step_limit
        self.builtins = {
            'CAR': car, 'CDR': cdr, 'CONS': cons, 'LIST': lambda *x: list(x) or None,
            'APPEND': lambda *xs: sum((seq(x) for x in xs), []) or None,
            'REVERSE': lambda x: list(reversed(seq(x))) or None,
            'LENGTH': lambda x: len(seq(x)), 'NTH': lambda i,x: x[i] if x and i < len(x) else None,
            'LAST': lambda x: x[-1:] if x else None,
            'ASSOC': lambda k,x: next((p for p in seq(x) if equal(car(p), k)), None),
            'MEMBER': lambda k,x: next((x[i:] for i,p in enumerate(seq(x)) if equal(k,p)), None),
            'SUBST': lambda new,old,x: [new if equal(p,old) else p for p in seq(x)] or None,
            'EQUAL': equal, '=': self.compare_equal,
            '/=': lambda a,b: not self.compare_equal(a,b), '<': lambda a,b: a<b, '<=': lambda a,b: a<=b,
            '>': lambda a,b: a>b, '>=': lambda a,b: a>=b,
            '+': lambda *xs: sum(xs), '*': lambda *xs: math.prod(xs),
            '-': lambda a,*xs: a-sum(xs) if xs else -a,
            '/': self.divide, '1+': lambda x:x+1, '1-': lambda x:x-1,
            'ABS': abs, 'SQRT': math.sqrt, 'COS': math.cos, 'SIN': math.sin,
            'ATAN': lambda y,x=None: math.atan(y) if x is None else math.atan2(y,x),
            'EXPT': pow, 'FIX': int, 'REM': lambda a,b: math.fmod(a,b),
            'MAX': max, 'MIN': min, 'TYPE': lisp_type, 'FLOAT': float, 'LOGAND': lambda a,b:a&b,
            'NUMBERP': lambda x: isinstance(x,(int,float)) and not isinstance(x,bool),
            'LISTP': lambda x: x is None or isinstance(x,(list,Pair)),
            'NULL': lambda x:not truth(x), 'NOT': lambda x:not truth(x),
            'STRCAT': lambda *xs: ''.join(xs), 'STRCASE': lambda x,lower=None:x.lower() if lower else x.upper(),
            'ITOA': str, 'ATOI': int, 'STRLEN': len, 'ASCII': lambda value: ord(value[0]), 'RTOS': lambda x,*opts: f'{x:.{opts[1] if len(opts)>1 else 4}f}',
            'VL-STRING-TRIM': lambda chars,value: value.strip(chars),
            'VL-SYMBOL-NAME': str, 'VL-STRING->LIST': lambda x:list(map(ord,x)),
            'VL-LIST->STRING': lambda xs: ''.join(map(chr,seq(xs))),
            'VL-STRING-MISMATCH': lambda a,b: next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y), min(len(a),len(b))),
            'VL-STRING-SEARCH': lambda token,textdata,offset=0: (i if (i:=textdata.find(token,offset))>=0 else None),
            'SUBSTR': lambda s,start,n=None:s[start-1:] if n is None else s[start-1:start-1+n],
            'VL-STRING-RIGHT-TRIM': lambda chars,value:value.rstrip(chars),
            'VL-PRIN1-TO-STRING': repr, 'VL-REMOVE': lambda x,xs:[y for y in seq(xs) if not equal(x,y)] or None,
            'PRINC': lambda *x: None, 'READ': lambda x:quoted(parse(x)[0]),
            'MAPCAR': lambda fn,*xs: [self.call(fn,list(a)) for a in zip(*(seq(x) for x in xs))] or None,
            'APPLY': lambda fn,xs:self.call(fn,seq(xs)),
            'VL-REMOVE-IF': lambda fn,xs:[x for x in seq(xs) if not truth(self.call(fn,[x]))] or None,
            'VL-REMOVE-IF-NOT': lambda fn,xs:[x for x in seq(xs) if truth(self.call(fn,[x]))] or None,
            'VL-SOME': lambda fn,xs:next((v for x in seq(xs) if truth(v:=self.call(fn,[x]))),None),
            'VL-EVERY': lambda fn,xs:all(truth(self.call(fn,[x])) for x in seq(xs)),
            'VL-SORT': lambda xs,fn: sorted(seq(xs),key=cmp_to_key(lambda a,b: -1 if truth(self.call(fn,[a,b])) else (1 if truth(self.call(fn,[b,a])) else 0))) or None,
            'VL-CATCH-ALL-APPLY': self.catch,
            'VL-CATCH-ALL-ERROR-P': lambda x:isinstance(x,CaughtError),
            'VL-CATCH-ALL-ERROR-MESSAGE': lambda x:str(x.exception),
        }
        for op in ['CADR','CADDR','CADDDR','CAAR','CDAR','CDDR','CDDDR','CADAR','CADR']:
            self.builtins[op] = self.accessor(op)

    @staticmethod
    def compare_equal(*values):
        # Documented = arguments are numbers or strings; NIL is not a number.
        for value in values:
            if value is None or value is False:
                raise TypeError('bad argument type: numberp: nil')
            if isinstance(value, (Symbol, bool)) or not isinstance(value, (int, float, str)):
                raise TypeError(f'bad argument type for =: {value!r}')
        return all(equal(value, values[0]) for value in values)

    @staticmethod
    def accessor(op):
        def access(x):
            for letter in reversed(op[1:-1]):
                x = car(x) if letter == 'A' else cdr(x)
            return x
        return access

    @staticmethod
    def divide(a, *xs):
        for b in xs:
            a = int(a/b) if isinstance(a,int) and isinstance(b,int) else a/b
        return a

    def catch(self, name, values):
        try: return self.call(name,seq(values))
        except Exception as exc: return CaughtError(exc)

    def lookup(self, key):
        for frame in reversed(self.frames):
            if key in frame: return frame[key]
        return None

    def set(self,key,value):
        for frame in reversed(self.frames):
            if key in frame:
                frame[key] = value
                return value
        self.frames[0][key] = value
        return value

    def evaluate(self, form):
        self.steps += 1
        if self.steps > self.step_limit: raise RuntimeError('test step limit')
        if isinstance(form,Symbol): return self.lookup(form)
        if not isinstance(form,list): return form
        if not form: return None
        op,*args = form
        if op in ('QUOTE','FUNCTION'): return quoted(args[0])
        if op == 'DEFUN':
            self.functions[args[0]] = (seq(args[1]),args[2:])
            return args[0]
        if op == 'SETQ':
            value = None
            for i in range(0,len(args),2): value=self.set(args[i],self.evaluate(args[i+1]))
            return value
        if op == 'PROGN': return self.body(args)
        if op == 'IF': return self.evaluate(args[1] if truth(self.evaluate(args[0])) else (args[2] if len(args)>2 else None))
        if op == 'AND':
            value = True
            for a in args:
                value = self.evaluate(a)
                if not truth(value): return None
            return value
        if op == 'OR':
            for a in args:
                if truth(value:=self.evaluate(a)): return value
            return None
        if op == 'COND':
            for clause in args:
                value = self.evaluate(clause[0])
                if truth(value): return self.body(clause[1:]) if len(clause)>1 else value
            return None
        # Date: 2026-10-12. VLAX-FOR receives a finite injected collection; no COM emulation.
        if op in ('FOREACH', 'VLAX-FOR'):
            value = None
            for item in seq(self.evaluate(args[1])):
                self.set(args[0],item)
                value=self.body(args[2:])
            return value
        if op == 'WHILE':
            value = None
            while truth(self.evaluate(args[0])): value=self.body(args[1:])
            return value
        if op == 'REPEAT':
            value = None
            for _ in range(self.evaluate(args[0])): value=self.body(args[1:])
            return value
        return self.call(op,[self.evaluate(a) for a in args])

    def body(self, forms):
        value=None
        for form in forms: value=self.evaluate(form)
        return value

    def call(self, name, values):
        if isinstance(name,list) and name[0] == 'LAMBDA':
            params,body=seq(name[1]),name[2:]
        elif name in self.builtins:
            value = self.builtins[name](*values)
            return None if value is False or value == [] else value
        elif name in self.functions:
            params,body=self.functions[name]
        else: raise RuntimeError(f'CAD API or unknown function called in pure test: {name}')
        split=params.index(Symbol('/')) if Symbol('/') in params else len(params)
        if len(values) != split: raise TypeError(f'{name}: expected {split}, got {len(values)}')
        frame=dict(zip(params[:split],values))
        frame.update({p:None for p in params[split+1:]})
        self.frames.append(frame)
        try: return self.body(body)
        finally: self.frames.pop()

    def load_definitions(self, path):
        for form in parse(path.read_text(encoding='utf-8')):
            if isinstance(form,list) and form[0] == 'DEFUN': self.evaluate(form)

    def run(self, code):
        self.steps=0
        return self.body(parse(code))
