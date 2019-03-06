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
        self.output = []
        self.last_word = None
        self.last_addr = 0
        self.last_op = None
        self.compiler = []
        self.wordlist = []
        self.fill_compiler()
        self.fill_wordlist()
        self.output.append(0)             # entry vector

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
        xt, _ = self.search(entry)
        self.output[0] = PRIMITIVES['BRANCH'] | xt.addr

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
                if w[0] == '$':
                    val = int(w[1:], 16)
                else:
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
        if xt == PRIMITIVES['EXIT']:
            if self.maybe_merge_exit():
                return
        self.last_op = self.here
        self.output.append(xt)

    def maybe_merge_exit(self):
        if self.last_op != self.here - 1:
            return False
        op = self.output[self.last_op]
        if op & PRIMITIVES['LIT'] or op & PRIMITIVES['0BRANCH'] == PRIMITIVES['0BRANCH']:
            return False
        if op & PRIMITIVES['BRANCH']:
            # just drop the EXIT
            return True
        if op & PRIMITIVES['CALL']:
            # convert CALL to BRANCH
            op = (op & ~PRIMITIVES['CALL']) | PRIMITIVES['BRANCH']
        elif op & PRIMITIVES['EXIT'] == PRIMITIVES['EXIT']:
            # already an EXIT, so ignore this one
            return True
        elif op & 0x30: # rstack op
            return False
        else:
            op |= PRIMITIVES['EXIT']
        self.output[self.last_op] = op
        return True


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
        self.last_op = None

    @primitive('BEGIN')
    def c_begin(self):
        self.push(self.here)
        self.last_op = None

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


    def addr2name(self, addr):
        for word in self.wordlist:
            if hasattr(word, 'addr') and word.addr == addr:
                return word.name

    def disassemble(self):
        inverse_ops = {v: k for k, v in PRIMITIVES.items()}

        out = ""
        for addr, w in enumerate(self.output):
            def o(s):
                nonlocal out
                name = self.addr2name(addr)
                if name:
                    out += "# %s\n" % name
                out += "% 4x: %04x\t# %s\n" % (addr, w, s)

            bop = w & PRIMITIVES['0BRANCH']
            iop = inverse_ops.get(w)

            if w & PRIMITIVES['LIT']:
                o("%d" % (w & 0x7fff))
            elif bop:
                bdest = w & 0x1fff
                name = self.addr2name(bdest)
                if name:
                    o("%s %s (%04x)" % (inverse_ops.get(bop), name, bdest))
                else:
                    o("%s %04x" % (inverse_ops.get(bop), bdest))
            elif iop:
                o(iop)
            elif w & PRIMITIVES['EXIT'] == PRIMITIVES['EXIT'] and inverse_ops.get(w & ~PRIMITIVES['EXIT']):
                o("%s EXIT" % inverse_ops.get(w & ~PRIMITIVES['EXIT']))
            else:
                o("<unknown>")

        return out


if __name__ == '__main__':
    c = ForthCompiler()
    c.evaluate("""
: ! !+ DROP ;
: delay begin dup while 1 - repeat drop ;
: toggle-blink ( n -- n ) 3 xor dup $100 ! ;
: init-io 3 $101 ! ;
: start init-io 1 begin 100 delay toggle-blink again ;
""")
    c.link()
    print(c.disassemble())
