import io
import array
import sys


def primitive(name):
    def decorator(fn):
        setattr(fn, 'name', name)
        return fn
    return decorator


MEMSIZE = 256
CODESIZE = 256

EXIT_BITS = 0x1030

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
    'EXIT':    0x1830,
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


class Literal:
    def __init__(self, name, val):
        self.name = name
        self.val = val

    def compile(self, forth):
        forth.compile_literal(self.val)


class ForthCompiler:
    def __init__(self):
        self.input = None
        self.lastch = None
        self.stack = []
        self.rstack = []
        self.state = 0
        self.output = []
        self.mem_pos = 0
        self.last_word = None
        self.last_addr = 0
        self.last_op = None
        self.compiler = []
        self.wordlist = []
        self.fill_compiler()
        self.fill_wordlist()
        self.output.append(0)             # entry vector

    def evaluate(self, text):
        if hasattr(text, 'read'):
            text = text.read()
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
        if self.here > CODESIZE:
            raise RuntimeError("code memory overflow: %d > %d", self.mem_pos, CODESIZE)
        if self.mem_pos > MEMSIZE:
            raise RuntimeError("data memory overflow: %d > %d", self.mem_pos, MEMSIZE)

    def warn(self, message):
        print('Warning: %s' % message, file=sys.stderr)

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
            op |= EXIT_BITS
        self.output[self.last_op] = op
        return True


    @property
    def here(self):
        return len(self.output)


    @primitive('(')
    def c_paren(self):
        self.parse(')')

    @primitive('\\')
    def c_backslash(self):
        self.parse('\n')

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
        if len(self.stack) > 0:
            self.warn("control flow stack is not balanced")

    @primitive('CONSTANT')
    def c_constant(self):
        val = self.pop()
        name = self.word()
        self.wordlist.insert(0, Literal(name, val))

    @primitive('VARIABLE')
    def c_variable(self):
        name = self.word()
        self.push(1)
        self.c_allot()
        addr = self.pop()
        self.wordlist.insert(0, Literal(name, addr))

    @primitive('ALLOT')
    def c_allot(self):
        count = self.pop()
        addr = self.mem_pos
        self.mem_pos += count
        self.push(addr)

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

    def binary(self):
        a = array.array('H', self.output)
        if sys.byteorder == 'little':
            a.byteswap()
        return a.tobytes()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser('forth compiler')
    parser.add_argument('sources', nargs='+', type=argparse.FileType('r'))
    parser.add_argument('--print-disassembly', action='store_true')
    parser.add_argument('--output', '-o', type=argparse.FileType('wb'))
    parser.add_argument('--output-hex', type=argparse.FileType('w'))
    args = parser.parse_args()

    if not args.output and not args.print_disassembly and not args.output_hex:
        parser.error('did you forget one of --output, --output-hex, or --print-disassembly?')

    c = ForthCompiler()
    for f in args.sources:
        c.evaluate(f)
    c.link()
    if args.print_disassembly:
        print(c.disassemble())
    if args.output:
        args.output.write(c.binary())
    if args.output_hex:
        for w in c.output:
            print("%04x" % w, file=args.output_hex)
