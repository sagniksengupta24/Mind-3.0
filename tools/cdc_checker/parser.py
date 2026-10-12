"""Structural SystemVerilog front end for the CDC checker.

Enforced synthesizable subset (anything outside raises :class:`InputError`
instead of being silently mis-analyzed):

* one or more ``module``/``endmodule`` blocks, ANSI C-style headers
  (``input``/``output``/``inout`` with optional ``logic``/``wire``/``reg``
  type and constant ``[msb:lsb]`` ranges)
* ``parameter``/``localparam`` with constant integer or simple arithmetic
  initializers (used for range evaluation)
* net/variable declarations (``wire``, ``reg``, ``logic``) with constant
  ranges; single unpacked memory dimension (``mem [0:N]``) allowed
* continuous ``assign`` statements
* ``always_ff @(posedge/negedge clk)``, ``always @(posedge/negedge clk …)``,
  ``always_comb`` / ``always @(*)`` blocks containing ``if``/``else``/``case``
  control flow with blocking/nonblocking assignments; ``for`` loops,
  ``while``, ``fork``, functions, tasks, ``generate`` blocks and
  ``$past``-style temporal constructs are rejected
* module instances with named (``.formal(actual)``) port connections;
  positional connections are rejected
* no ``interface``, ``package``, ``import``, ``typedef``, ``struct``,
  ``union``, ``assert``/``assume``/``cover``, preprocessor directives
  other than benign ```timescale``

The parser is tokenizer-driven (comments/strings respected, paren/bracket
depth tracked); it is not a regular-expression skim of the source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class InputError(ValueError):
    """Raised when RTL falls outside the enforced synthesizable subset."""


_KEYWORDS = frozenset({
    "module", "endmodule", "input", "output", "inout", "wire", "reg",
    "logic", "parameter", "localparam", "assign", "always", "always_ff",
    "always_comb", "always_latch", "begin", "end", "if", "else", "case",
    "endcase", "casex", "casez", "default", "for", "while", "do", "foreach",
    "function", "endfunction", "task", "endtask", "generate", "endgenerate",
    "genvar", "interface", "endinterface", "package", "endpackage",
    "import", "typedef", "struct", "union", "assert", "assume", "cover",
    "property", "sequence", "posedge", "negedge", "edge", "or", "and",
})

_SYS_FUNCS = frozenset({"$clog2", "$bits", "$past", "$rose", "$fell", "$stable"})

_TOKEN_RE = re.compile(r"""
    (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<number>\d+'[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\d+(?:\.\d+)?)
  | (?P<sysfunc>\$[A-Za-z_]\w*)
  | (?P<ident>[A-Za-z_]\w*)
  | (?P<op><=|>=|==|!=|&&|\|\||<<|>>|\|->|\|=>|\#\#|::|[+\-*/%<>=!&|^~?:;,.@(){}\[\]\#])
""", re.VERBOSE)


def tokenize(text: str) -> list[str]:
    """Split source into tokens after removing comments (strings respected)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            m = re.match(r'"(?:[^"\\]|\\.)*"', text[i:])
            if not m:
                raise InputError("Unterminated string literal.")
            out.append(m.group(0))
            i += len(m.group(0))
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                raise InputError("Unterminated block comment.")
            i = j + 2
        elif ch.isspace():
            i += 1
        else:
            m = _TOKEN_RE.match(text, i)
            if not m:
                raise InputError(f"Unrecognized source text near: {text[i:i + 40]!r}")
            out.append(m.group(0))
            i += len(m.group(0))
    return out


def _is_number(tok: str) -> bool:
    return bool(re.fullmatch(r"\d+'[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\d+(?:\.\d+)?", tok))


def identifiers_of(tokens: list[str]) -> list[str]:
    """Identifier references in a token stream (declarations excluded by caller)."""
    refs: list[str] = []
    skip_next = False
    for idx, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if tok in _SYS_FUNCS and tok not in ("$clog2", "$bits"):
            raise InputError(f"Temporal/system construct {tok} outside the subset.")
        if tok.startswith("$"):
            continue
        if tok in _KEYWORDS:
            continue
        if _is_number(tok) or (tok.startswith('"')):
            continue
        if re.fullmatch(r"[A-Za-z_]\w*", tok or ""):
            # A bare type name following a direction keyword is a declaration,
            # not a reference; callers strip declarations before calling here.
            refs.append(tok)
    return refs


@dataclass
class Port:
    name: str
    direction: str  # input | output | inout
    width: int


@dataclass
class Assign:
    lhs: str
    rhs_ids: list[str]


@dataclass
class AlwaysBlock:
    kind: str  # seq | comb
    clocks: list[tuple[str, str]]  # (edge, signal) for seq; [] for comb
    drivers: list[Assign] = field(default_factory=list)  # lhs <- rhs_ids


@dataclass
class Instance:
    module: str
    name: str
    connections: dict[str, list[str]] = field(default_factory=dict)  # formal -> actual ids


@dataclass
class Module:
    name: str
    ports: dict[str, Port] = field(default_factory=dict)
    widths: dict[str, int] = field(default_factory=dict)  # every declared signal -> width
    params: dict[str, int] = field(default_factory=dict)
    assigns: list[Assign] = field(default_factory=list)
    always_blocks: list[AlwaysBlock] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)


def _eval_int(expr_tokens: list[str], params: dict[str, int]) -> int:
    """Evaluate a constant integer expression with parameter substitution."""
    expr = "".join(expr_tokens)
    def sub(m: re.Match[str]) -> str:
        name = m.group(0)
        if name in params:
            return str(params[name])
        raise InputError(f"Non-constant range element: {name!r}")
    expr = re.sub(r"[A-Za-z_]\w*", sub, expr)
    if not re.fullmatch(r"[0-9+\-*/() ]+", expr):
        raise InputError(f"Non-constant range expression: {expr!r}")
    try:
        value = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 - validated charset above
    except Exception as exc:
        raise InputError(f"Bad range expression: {expr!r}") from exc
    if not isinstance(value, int):
        raise InputError(f"Non-integer range expression: {expr!r}")
    return value


def _split_top_commas(tokens: list[str]) -> list[list[str]]:
    parts, depth, cur = [], 0, []
    for tok in tokens:
        if tok in "([":
            depth += 1
        elif tok in ")]":
            depth -= 1
        if tok == "," and depth == 0:
            parts.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        parts.append(cur)
    return parts


def _parse_range(tokens: list[str], params: dict[str, int]) -> tuple[int, list[str]]:
    """Parse ``[msb:lsb]`` prefix; return (width, remaining tokens)."""
    if not tokens or tokens[0] != "[":
        return 1, tokens
    depth, idx = 0, 0
    for idx, tok in enumerate(tokens):
        if tok == "[":
            depth += 1
        elif tok == "]":
            depth -= 1
            if depth == 0:
                break
    inner = tokens[1:idx]
    rest = tokens[idx + 1:]
    if ":" in inner:
        colon = inner.index(":")
        msb = _eval_int(inner[:colon], params)
        lsb = _eval_int(inner[colon + 1:], params)
        width = abs(msb - lsb) + 1
    else:
        # Single unpacked memory dimension, e.g. `mem [0:7]`: element width 1
        # here; the element declaration carries the real width separately.
        _eval_int(inner, params)
        return 1, rest
    return width, rest


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.toks = tokens
        self.pos = 0

    def peek(self) -> str:
        return self.toks[self.pos] if self.pos < len(self.toks) else ""

    def next(self) -> str:
        tok = self.peek()
        self.pos += 1
        return tok

    def expect(self, tok: str) -> None:
        got = self.next()
        if got != tok:
            raise InputError(f"Expected {tok!r}, found {got!r}.")

    def parse_module(self) -> Module:
        if self.next() != "module":
            raise InputError("Expected 'module'.")
        name = self.next()
        if not re.fullmatch(r"[A-Za-z_]\w*", name or ""):
            raise InputError(f"Bad module name: {name!r}.")
        mod = Module(name=name)
        # Optional #(...) parameter header.
        if self.peek() == "#":
            self.next()
            self.expect("(")
            self._parse_param_list(mod)
            self.expect(")")
        self.expect("(")
        header: list[str] = []
        depth = 1
        while depth:
            tok = self.next()
            if not tok:
                raise InputError("Unterminated module header.")
            if tok == "(":
                depth += 1
            elif tok == ")":
                depth -= 1
                if depth == 0:
                    break
            header.append(tok)
        self.expect(";")
        self._parse_ports(header, mod)
        self._parse_body(mod)
        if self.next() != "endmodule":
            raise InputError(f"Module {name}: expected 'endmodule'.")
        return mod

    def _parse_param_list(self, mod: Module) -> None:
        for part in _split_top_commas(self._collect_until(")")):
            # `parameter NAME = value` (type keywords tolerated and skipped)
            toks = [t for t in part if t not in ("parameter", "localparam", "integer", "string")]
            if len(toks) >= 3 and toks[1] == "=" and re.fullmatch(r"[A-Za-z_]\w*", toks[0] or ""):
                mod.params[toks[0]] = _eval_int(toks[2:], mod.params)
            elif toks:
                raise InputError(f"Unsupported parameter declaration: {' '.join(toks)}")

    def _collect_until(self, stop: str) -> list[str]:
        out, depth = [], 0
        while True:
            tok = self.next()
            if not tok:
                raise InputError(f"Unterminated construct before {stop!r}.")
            if tok in "([":
                depth += 1
            elif tok in ")]":
                if tok == stop and depth == 0:
                    self.pos -= 1  # let caller consume the stop token
                    return out
                depth -= 1
            out.append(tok)

    def _parse_ports(self, header: list[str], mod: Module) -> None:
        direction: str | None = None
        for part in _split_top_commas(header):
            if not part:
                continue
            if part[0] in ("input", "output", "inout"):
                direction = part[0]
                part = part[1:]
            if direction is None:
                raise InputError("Port without direction (ANSI direction required).")
            while part and part[0] in ("wire", "reg", "logic", "tri", "signed"):
                part = part[1:]
            width, part = _parse_range(part, mod.params)
            for pname in part:
                if pname == ",":
                    continue
                if not re.fullmatch(r"[A-Za-z_]\w*", pname or ""):
                    raise InputError(f"Bad port name: {pname!r}.")
                mod.ports[pname] = Port(name=pname, direction=direction, width=width)
                mod.widths[pname] = width

    def _parse_body(self, mod: Module) -> None:
        while self.peek() not in ("endmodule", ""):
            tok = self.peek()
            if tok in ("parameter", "localparam"):
                self.next()
                rest: list[str] = []
                while self.peek() not in (";", ""):
                    rest.append(self.next())
                self.expect(";")
                toks = [t for t in rest if t not in ("integer", "string")]
                if len(toks) >= 3 and toks[1] == "=" and re.fullmatch(r"[A-Za-z_]\w*", toks[0] or ""):
                    mod.params[toks[0]] = _eval_int(toks[2:], mod.params)
                else:
                    raise InputError(f"Unsupported parameter declaration: {' '.join(rest)}")
            elif tok in ("input", "output", "inout", "wire", "reg", "logic", "tri"):
                self._parse_decl(mod)
            elif tok == "assign":
                self.next()
                lhs_toks: list[str] = []
                while self.peek() not in ("=", ""):
                    lhs_toks.append(self.next())
                self.expect("=")
                rhs: list[str] = []
                while self.peek() not in (";", ""):
                    rhs.append(self.next())
                self.expect(";")
                for target in self._lhs_targets(lhs_toks):
                    mod.assigns.append(Assign(lhs=target, rhs_ids=identifiers_of(rhs)))
            elif tok in ("always", "always_ff", "always_comb", "always_latch"):
                mod.always_blocks.append(self._parse_always())
            elif re.fullmatch(r"[A-Za-z_]\w*", tok or "") and self._looks_like_instance():
                mod.instances.append(self._parse_instance())
            elif tok == ";":
                self.next()
            else:
                raise InputError(
                    f"Unsupported construct {tok!r} in module {mod.name} "
                    "(only declarations, assign, always blocks, named instances)."
                )

    def _parse_decl(self, mod: Module) -> None:
        toks: list[str] = []
        while self.peek() not in (";", ""):
            toks.append(self.next())
        self.expect(";")
        if toks and toks[0] in ("input", "output", "inout"):
            toks = toks[1:]
        while toks and toks[0] in ("wire", "reg", "logic", "tri", "signed"):
            toks = toks[1:]
        width, toks = _parse_range(toks, mod.params)
        for part in _split_top_commas(toks):
            if not part:
                continue
            pname = part[0]
            if not re.fullmatch(r"[A-Za-z_]\w*", pname or ""):
                raise InputError(f"Bad declaration name: {pname!r}.")
            if "=" in part:
                raise InputError("Inline initialization in declarations is outside the subset.")
            # A trailing unpacked dimension (e.g. `mem [0:7]`) only sizes
            # storage; the element width was already parsed above.
            mod.widths[pname] = width

    def _looks_like_instance(self) -> bool:
        # IDENT [ #(...) ] IDENT (
        i = self.pos
        if not re.fullmatch(r"[A-Za-z_]\w*", self.toks[i] if i < len(self.toks) else ""):
            return False
        i += 1
        if i < len(self.toks) and self.toks[i] == "#":
            i += 1
            if i >= len(self.toks) or self.toks[i] != "(":
                return False
            depth = 0
            while i < len(self.toks):
                if self.toks[i] == "(":
                    depth += 1
                elif self.toks[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        if i + 1 >= len(self.toks):
            return False
        return bool(re.fullmatch(r"[A-Za-z_]\w*", self.toks[i] or "")) and self.toks[i + 1] == "("

    def _parse_instance(self) -> Instance:
        modname, instname = self.next(), ""
        if self.peek() == "#":
            self.next()
            self.expect("(")
            depth = 1
            while depth:
                tok = self.next()
                if tok == "(":
                    depth += 1
                elif tok == ")":
                    depth -= 1
        instname = self.next()
        self.expect("(")
        inst = Instance(module=modname, name=instname)
        while self.peek() not in (")", ""):
            if self.next() != ".":
                raise InputError("Only named (.formal(actual)) port connections are supported.")
            formal = self.next()
            self.expect("(")
            actual: list[str] = []
            depth = 1
            while depth:
                tok = self.next()
                if not tok:
                    raise InputError("Unterminated instance port connection.")
                if tok == "(":
                    depth += 1
                elif tok == ")":
                    depth -= 1
                    if depth == 0:
                        break
                actual.append(tok)
            inst.connections[formal] = identifiers_of(actual)
            if self.peek() == ",":
                self.next()
        self.expect(")")
        self.expect(";")
        return inst

    def _parse_always(self) -> AlwaysBlock:
        kind_tok = self.next()
        clocks: list[tuple[str, str]] = []
        kind = "comb"
        if self.peek() == "@":
            self.next()
            if self.peek() == "*":
                # Bare `always @*`: combinational, no clock.
                self.next()
            else:
                self.expect("(")
                sens: list[str] = []
                depth = 1
                while depth:
                    tok = self.next()
                    if not tok:
                        raise InputError("Unterminated sensitivity list.")
                    if tok == "(":
                        depth += 1
                    elif tok == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    sens.append(tok)
                clocks = self._parse_sensitivity(sens)
                kind = "seq" if clocks else "comb"
        elif kind_tok == "always_ff":
            raise InputError("always_ff requires an event sensitivity list.")
        block = AlwaysBlock(kind=kind, clocks=clocks)
        body = self._collect_statement()
        self._collect_drivers(body, block)
        return block

    def _parse_sensitivity(self, sens: list[str]) -> list[tuple[str, str]]:
        if sens == ["*"]:
            return []
        clocks = []
        for part in _split_top_commas(sens):
            if not part:
                continue
            if part[0] in ("posedge", "negedge") and len(part) == 2 and re.fullmatch(r"[A-Za-z_]\w*", part[1] or ""):
                clocks.append((part[0], part[1]))
            else:
                # Level/combinational sensitivity -> combinational block.
                return []
        return clocks

    def _collect_statement(self) -> list[str]:
        toks: list[str] = []
        tok = self.next()
        if tok == "begin":
            toks.append(tok)
            depth = 1
            while depth:
                tok = self.next()
                if not tok:
                    raise InputError("Unterminated begin/end block.")
                toks.append(tok)
                if tok == "begin":
                    depth += 1
                elif tok == "end":
                    depth -= 1
            return toks
        # Single statement terminated by ';' (but not a nested for/function).
        toks.append(tok)
        if tok == "for":
            raise InputError("'for' loops are outside the enforced subset.")
        if tok in ("function", "task", "generate"):
            raise InputError(f"'{tok}' blocks are outside the enforced subset.")
        depth_p = 0
        while True:
            if tok in "([":
                depth_p += 1
            elif tok in ")]":
                depth_p -= 1
            if tok == ";" and depth_p <= 0:
                break
            tok = self.next()
            if not tok:
                raise InputError("Unterminated statement.")
            toks.append(tok)
        return toks

    def _collect_drivers(self, body: list[str], block: AlwaysBlock) -> None:
        # Split top-level ';' statements. begin/end nesting is transparent
        # (stripped per statement below); only parenthesis depth suppresses
        # splitting, so `if (c) lhs <= e;` separates correctly.
        stmts, depth_p, cur = [], 0, []
        for tok in body:
            if tok in "([":
                depth_p += 1
            elif tok in ")]":
                depth_p -= 1
            if tok == ";" and depth_p <= 0:
                stmts.append(cur)
                cur = []
            else:
                cur.append(tok)
        for stmt in stmts:
            if "for" in stmt or "while" in stmt:
                raise InputError("'for'/'while' loops are outside the enforced subset.")
            if "<=" in stmt:
                idx = stmt.index("<=")
                lhs_toks, rhs = stmt[:idx], stmt[idx + 1:]
            elif "=" in stmt and stmt[0] not in ("==",):
                # Avoid '==' / '<=' confusion: find a bare '=' operator token.
                try:
                    idx = stmt.index("=")
                except ValueError:
                    continue
                lhs_toks, rhs = stmt[:idx], stmt[idx + 1:]
            else:
                continue
            # Strip leading control-flow keywords and parenthesized
            # conditions: `begin if (cond) lhs <= …`, `else lhs <= …`,
            # `end else if (cond) lhs <= …`, case-item prefixes.
            while lhs_toks and lhs_toks[0] in ("if", "else", "case", "casex", "casez", "default", "begin", "end"):
                lhs_toks = lhs_toks[1:]
                if lhs_toks and lhs_toks[0] == "(":
                    depth_p, idx = 0, 0
                    for idx, tok in enumerate(lhs_toks):
                        if tok == "(":
                            depth_p += 1
                        elif tok == ")":
                            depth_p -= 1
                            if depth_p == 0:
                                break
                    lhs_toks = lhs_toks[idx + 1:]
            # Case-item label prefix: `2'b00: y` or `default: y`.
            # Bracket depth tracked so bit-selects (`mem[i]`) are untouched.
            if ":" in lhs_toks:
                depth_p = 0
                for idx, tok in enumerate(lhs_toks):
                    if tok in "([":
                        depth_p += 1
                    elif tok in ")]":
                        depth_p -= 1
                    elif tok == ":" and depth_p == 0:
                        lhs_toks = lhs_toks[idx + 1:]
                        break
            if not lhs_toks or lhs_toks[0] == "(":
                continue  # condition expression, not an assignment
            for target in self._lhs_targets(lhs_toks):
                block.drivers.append(Assign(lhs=target, rhs_ids=identifiers_of(rhs)))

    def _lhs_targets(self, lhs_toks: list[str]) -> list[str]:
        # Flatten concatenations '{a, b}' and strip bit-selects: a[i] -> a.
        targets = []
        for chunk in _split_top_commas([t for t in lhs_toks if t not in ("{", "}")]):
            if not chunk:
                continue
            name = chunk[0]
            if not re.fullmatch(r"[A-Za-z_]\w*", name or ""):
                raise InputError(f"Bad assignment target: {' '.join(chunk)}")
            targets.append(name)
        if not targets:
            raise InputError("Empty assignment target.")
        return targets


def parse_modules(text: str) -> dict[str, Module]:
    """Parse all modules in one SystemVerilog source file."""
    if re.search(r"^\s*`(?!timescale)", text, re.M):
        raise InputError("Preprocessor directives (other than `timescale) are outside the subset.")
    tokens = tokenize(text)
    parser = _Parser(tokens)
    modules: dict[str, Module] = {}
    while parser.pos < len(tokens):
        if parser.peek() == ";":
            parser.next()
            continue
        mod = parser.parse_module()
        if mod.name in modules:
            raise InputError(f"Duplicate module {mod.name}.")
        modules[mod.name] = mod
    if not modules:
        raise InputError("No module found.")
    return modules


def load_top(rtl_path: str, top: str) -> Module:
    """Load and parse the top module from an RTL file."""
    try:
        with open(rtl_path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise InputError(f"Cannot read RTL file: {exc}") from exc
    modules = parse_modules(text)
    if top not in modules:
        raise InputError(f"Top module {top!r} not found (have: {sorted(modules)}).")
    return modules[top]
