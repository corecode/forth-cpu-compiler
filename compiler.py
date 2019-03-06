import io

def primitive(name):
    def decorator(fn):
        setattr(fn, 'name', name)
        return fn
    return decorator


PRIMITIVES = {
    'NOP':     0x0800,
    'INVERT':  0x0700,
    '2/':      0x0200,
    '0=':      0x0300,
    'AND':     0x06c0,
    'OR':      0x05c0,
    'XOR':     0x04c0,
    '+':       0x00c0,
    '-':       0x01c0,
    'DUP':     0x0840,
    'SWAP':    0x0980,
    'DROP':    0x09c0,
    '>R':      0x09d0,
    'R>':      0x0a70,
    'R@':      0x0a40,
    'BRANCH':  0x4000,
    '0BRANCH': 0x6000,
    'CALL':    0x2000,
    'EXECUTE': 0x09e0,
    'EXIT':    0x1030,
    '!+':      0x0dc0,
    '@':       0x0c00,
    'LIT':     0x8000,
}


class Thread:
    def __init__(self, name, addr):
        self.name = name
        self.addr = addr

    def compile(self, forth):
        forth.comma(PRIMITIVES['CALL'] | self.addr)


class Primitive:
    def __init__(self, name, op):
        self.name = name
        self.op = op

    def compile(self, forth):
        forth.comma(self.op)


class ForthCompiler:
    def __init__(self):
        self.input = None
        self.lastch = None
        self.stack = []
        self.rstack = []
        self.state = 0
        self.output = [0]                 # entry vector
        self.compiler = []
        self.wordlist = []
        self.fill_compiler()
        self.fill_wordlist()

    def evaluate(self, text):
        self.input = text
        while True:
            w = self.word()
            if w == "": break
            try:
                self.eval(w)
            except Exception as e:
                raise RuntimeError("%s while processing word `%s'" % (e, w)) from e

    def link(self, entry='start'):
        # insert call
        return self.output


    def push(self, val):
        self.stack.append(val)

    def pop(self):
        return self.stack.pop()

    def fill_compiler(self):
        for f in dir(self):
            fn = getattr(self, f)
            name = getattr(fn, 'name', None)
            if name:
                self.compiler.insert(0, fn)

    def fill_wordlist(self):
        for n, op in PRIMITIVES.items():
            self.wordlist.insert(0, Primitive(n, op))

    def search(self, word, wordlist=None):
        for xt in wordlist or self.wordlist:
            if xt.name.lower() == word.lower():
                return xt, False
        return None, None

    def parse(self, delim):
        if not self.input: return ""
        word, *rest = self.input.split(delim, maxsplit=1)
        self.input = rest and rest[0] or ""
        return word

    def word(self):
        return self.parse(None)

    def eval(self, w):
        xt, _ = self.search(w, self.compiler)
        if xt:
            xt()
            return

        xt, immed = self.search(w)
        if xt is not None:
            if immed or not self.state:
                self.execute(xt)
            else:
                self.compile_comma(xt)
        else:
            try:
                val = int(w)
                if self.state:
                    self.compile_literal(val)
                else:
                    self.push(val)
            except ValueError:
                raise RuntimeError("unknown word `%s'" % w) from None

    def execute(self, xt):
        xt()

    def compile_literal(self, val):
        if val & 0x8000:
            self.comma(PRIMITIVES['LIT'] | ~val)
            self.comma(PRIMITIVES['INVERT'])
        else:
            self.comma(0x8000 | val)

    def compile_comma(self, xt):
        xt.compile(self)

    def comma(self, xt):
        self.output.append(xt)


    @property
    def here(self):
        return len(self.output)


    @primitive('(')
    def c_paren(self):
        self.parse(')')

    @primitive(':')
    def c_colon(self):
        self.last_word = self.word()
        self.last_xt = self.here
        self.state = 1

    @primitive(';')
    def c_semicolon(self):
        self.comma(PRIMITIVES['EXIT'])
        self.wordlist.insert(0, Thread(self.last_word, self.last_xt))
        self.state = 0

    @primitive('IF')
    def c_if(self):
        self.push(self.here)
        self.comma(PRIMITIVES['0BRANCH'])

    @primitive('THEN')
    def c_then(self):
        orig = self.pop()
        self.output[orig] |= self.here

    @primitive('BEGIN')
    def c_begin(self):
        self.push(self.here)
        self.comma(0)

    @primitive('AGAIN')
    def c_again(self):
        dest = self.pop()
        self.comma(PRIMITIVES['BRANCH'] | dest)

    @primitive('UNTIL')
    def c_until(self):
        self.c_then()

    @primitive('AHEAD')
    def c_ahead(self):
        self.push(self.here)
        self.comma(PRIMITIVES['BRANCH'])

    @primitive('WHILE')
    def c_while(self):
        dest = self.pop()
        self.c_if()
        self.push(dest)

    @primitive('REPEAT')
    def c_repeat(self):
        self.c_again()
        self.c_then()

    @primitive('ELSE')
    def c_else(self):
        orig = self.pop()
        self.c_ahead()
        self.push(orig)
        self.c_then()


if __name__ == '__main__':
    c = ForthCompiler()
    c.evaluate("""
: ! !+ DROP ;
: delay begin dup while 1 - repeat ;
: toggle-blink ( n -- n ) 3 xor dup 100 ! ;
: init-io 3 101 ! ;
: start init-io 1 begin 100 delay toggle-blink again ;
""")
    c.link()
    print(c.stack)
    for w in c.output:
        print("%04x" % w)
