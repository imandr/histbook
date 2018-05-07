#!/usr/bin/env python

# Copyright (c) 2017, DIANA-HEP
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# 
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# 
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import ast
import itertools
import math

import meta
import numpy

class ExpressionError(Exception): pass

class Dim(object):
    def __init__(self, names, expr):
        self.names = names
        self.expr = expr

    def __repr__(self):
        return "Dim({0}, {1})".format(repr(self.names), repr(self.expr))

    def __str__(self):
        return repr(self)

class Expr(object):
    def __repr__(self):
        return "{0}({1})".format(self.__class__.__name__, ", ".join(self._reprargs()))

    def __ne__(self, other):
        return not self.__eq__(other)

    recognized = {
        math.sqrt: "sqrt",
        numpy.sqrt: "sqrt",
        }

    @staticmethod
    def parse(expression):
        inverse = {"==": "!=",
                   "!=": "==",
                   "<":  ">=",
                   "<=": ">",
                   ">":  "<=",
                   ">=": "<",
                   "in": "not in",
                   "not in": "in"}

        calculate = {"+": lambda x, y: x + y,
                     "-": lambda x, y: x - y,
                     "*": lambda x, y: x * y,
                     "/": lambda x, y: x / y,
                     "//": lambda x, y: x // y,
                     "%": lambda x, y: x % y,
                     "**": lambda x, y: x ** y,
                     "|": lambda x, y: x | y,
                     "&": lambda x, y: x & y,
                     "^": lambda x, y: x ^ y}

        def not_(expr):
            if isinstance(expr, Relation):
                return Relation(inverse[expr.cmp], expr.arg, expr.const)
            elif isinstance(expr, And):
                return Or(*[not_(x) for x in expr.args])
            elif isinstance(expr, Or):
                notlogical = [not_(x) for x in expr.args if not isinstance(x, And)]
                logical    = [not_(x) for x in expr.args if     isinstance(x, And)]
                if len(logical) == 0:
                    return And(*notlogical)
                else:
                    return Or(*[And(*([x] + notlogical)) for x in logical])
            else:
                raise AssertionError(expr)

        def and_(*exprs):
            ands       = [x for x in exprs if isinstance(x, And)]
            ors        = [x for x in exprs if isinstance(x, Or)]
            notlogical = [x for x in exprs if not isinstance(x, (And, Or))]
            for x in ands:
                notlogical += x.args
            ors += [Or(*notlogical)]
            out = Or(*[And(*args) for args in itertools.product([x.args for x in ors])])
            if len(out.args) == 0:
                raise AssertionError(out)
            elif len(out.args) == 1:
                return out.args[0]
            else:
                return out

        def or_(*exprs):
            ors    = [x for x in exprs if isinstance(x, Or)]
            others = [x for x in exprs if not isinstance(x, Or)]
            for x in ors:
                others += x.args
            return Or(*others)

        def resolve(node):
            if isinstance(node, ast.Attribute):
                return getattr(resolve(node.value), node.attr)
            elif isinstance(node, ast.Name):
                return globals()[node.id]
            else:
                raise ExpressionError("not a function name: {0}".format(meta.dump_python_source(node).strip()))

        names = []
        def recurse(node, relations=False, intervals=False):
            if isinstance(node, ast.Num):
                return Const(node.n)

            elif isinstance(node, ast.Str):
                return Const(node.s)

            elif isinstance(node, ast.Dict) and len(node.keys) == 0:
                return Const(set())

            elif isinstance(node, ast.Set):
                content = [recurse(x) for x in node.elts]
                if all(isinstance(x, Const) for x in content):
                    return Const(set(x.value for x in content))
                else:
                    raise ExpressionError("sets in expressions may not contain variable contents: {0}".format(meta.dump_python_source(node).strip()))

            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                return Name(node.id)

            elif relations and isinstance(node, ast.Compare) and len(ops) == 1:
                if   isinstance(node.ops[0], ast.Eq):    cmp = "=="
                elif isinstance(node.ops[0], ast.NotEq): cmp = "!="
                elif isinstance(node.ops[0], ast.Lt):    cmp = "<"
                elif isinstance(node.ops[0], ast.LtE):   cmp = "<="
                elif isinstance(node.ops[0], ast.Gt):    cmp = ">"
                elif isinstance(node.ops[0], ast.GtE):   cmp = ">="
                elif isinstance(node.ops[0], ast.In):    cmp = "in"
                elif isinstance(node.ops[0], ast.NotIn): cmp = "not in"
                else:
                    raise ExpressionError("only comparision relations supported: '==', '!=', '<', '<=', '>', '>=', 'in', and 'not in': {0}".format(meta.dump_python_source(node).strip()))

                left = recurse(node.left)
                right = recurse(node.comparators[0])
                if not isinstance(left, Const) and isinstance(right, Const):
                    return Relation(cmp, left, right)
                elif isinstance(left, Const) and not isinstance(right, Const):
                    return Relation(inverse[cmp], right, left)
                else:
                    raise ExpressionError("comparisons must relate an unknown expression to a known constant: {0}".format(meta.dump_python_source(node).strip()))

            elif intervals and isinstance(node, ast.Compare) and len(ops) == 2:
                if isinstance(node.ops[0], ast.LtE) and isinstance(node.ops[1], ast.Lt):
                    low = recurse(node.left)
                    high = recurse(node.comparators[1])
                    lowclosed = True
                elif isinstance(node.ops[0], ast.Lt) and isinstance(node.ops[1], ast.LtE):
                    low = recurse(node.left)
                    high = recurse(node.comparators[1])
                    lowclosed = False
                elif isinstance(node.ops[0], ast.Gt) and isinstance(node.ops[1], ast.GtE):
                    low = recurse(node.comparators[1])
                    high = recurse(node.left)
                    lowclosed = True
                elif isinstance(node.ops[0], ast.GtE) and isinstance(node.ops[1], ast.Gt):
                    low = recurse(node.comparators[1])
                    high = recurse(node.left)
                    lowclosed = False
                else:
                    raise ExpressionError("interval comparisons may be A <= x < B, A < x <= B, A > x >= B, A >= x > B, but no other combination: {0}".format(meta.dump_python_source(node).strip()))

                arg = recurse(node.comparators[0])
                if isinstance(low, Const) and isinstance(high, Const) and not isinstance(arg, Const):
                    return Interval(arg, low, high, lowclosed=lowclosed)
                else:
                    raise ExpressionError("interval comparisons must have known constants on the low and high edge with an unknown expression in the middle: {0}".format(meta.dump_python_source(node).strip()))

            elif isinstance(node, ast.Compare):
                raise ExpressionError("comparison operators are only allowed at the top of an expression and only interval ranges are allowed to be chained: {0}".format(meta.dump_python_source(node).strip()))

            elif relations and isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                return not_(recurse(node.operand, relations=True))

            elif relations and isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
                return and_(*[recurse(x, relations=True) for x in node.values])

            elif relations and isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                return or_(*[recurse(x, relations=True) for x in node.values])

            elif isinstance(node, ast.BoolOp):
                raise ExpressionError("logical operators are only allowed at the top of an expression: {0}".format(meta.dump_python_source(node).strip()))
                
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                content = recurse(node.operand)
                if isinstance(content, UnaryOp) and content.fcn == "-":
                    return content
                else:
                    return UnaryOp("-", content)

            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
                return recurse(node.operand)

            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
                content = recurse(node.operand)
                if isinstance(content, UnaryOp) and content.fcn == "~":
                    return content
                else:
                    return UnaryOp("~", content)

            elif isinstance(node, ast.UnaryOp):
                raise ExpressionError("only unary operators supported: 'not', '-', '+', and '~': {0}".format(meta.dump_python_source(node).strip()))

            elif isinstance(node, ast.BinOp):
                if   isinstance(node.op, ast.Add):      fcn = "+"
                elif isinstance(node.op, ast.Sub):      fcn = "-"
                elif isinstance(node.op, ast.Mult):     fcn = "*"
                elif isinstance(node.op, ast.Div):      fcn = "/"
                elif isinstance(node.op, ast.FloorDiv): fcn = "//"
                elif isinstance(node.op, ast.Mod):      fcn = "%"
                elif isinstance(node.op, ast.Pow):      fcn = "**"
                elif isinstance(node.op, ast.BitOr):    fcn = "|"
                elif isinstance(node.op, ast.BitAnd):   fcn = "&"
                elif isinstance(node.op, ast.BitXor):   fcn = "^"
                else:
                    raise ExpressionError("only binary operators supported: '+', '-', '*', '/', '//', '%', '**', '|', '&', and '^': {0}".format(meta.dump_python_source(node).strip()))

                left = recurse(node.left)
                right = recurse(node.right)

                if isinstance(left, Const) and isinstance(right, Const):
                    return Const(calculate[fcn](left.value, right.value))
                elif isinstance(left, BinOp) and left.fcn == fcn and isinstance(right, BinOp) and right.fcn == fcn:
                    return BinOp(fcn, left.args + right.args)
                elif isinstance(left, BinOp) and left.fcn == fcn:
                    return BinOp(fcn, left.args + (right,))
                elif isinstance(right, BinOp) and right.fcn == fcn:
                    return BinOp(fcn, (left,) + right.args)
                else:
                    return BinOp(fcn, (left, right))

            elif isinstance(node, ast.Call):
                if node.func.id in Expr.recognized.values():
                    fcn = node.func.id
                else:
                    fcn = Expr.recognized.get(resolve(node.func), None)
                if fcn is None:
                    raise ExpressionError("unhandled function in expression: {0}".format(meta.dump_python_source(node).strip()))
                return Call(fcn, tuple(recurse(x) for x in node.args))

            else:
                ExpressionError("unhandled syntax in expression: {0}".format(meta.dump_python_source(node).strip()))

        if callable(expression):
            fcn = meta.decompiler.decompile_func(expression)
            if isinstance(fcn, ast.FunctionDef) and len(fcn.body) == 1 and isinstance(fcn.body[0], ast.Return):
                return Dim(names, recurse(fcn.body[0].value, relations=True, intervals=True))
            elif isinstance(fcn, ast.Lambda):
                return Dim(names, recurse(fcn.body.value, relations=True, intervals=True))
        else:
            mod = ast.parse(expression)
            if len(mod.body) == 1 and isinstance(mod.body[0], ast.Expr):
                return Dim(names, recurse(mod.body[0].value, relations=True, intervals=True))

        raise TypeError("expression must be a one-line string, one-line function, or lambda expression, not {0}".format(repr(expression)))

class Const(Expr):
    def __init__(self, value):
        self.value = value

    def _reprargs(self):
        return (repr(self.value),)

    def __str__(self):
        return str(self.value)

    def __hash__(self):
        if isinstance(self.value, set):
            value = (set, tuple(sorted(self.value)))
        else:
            value = self.value
        return hash((Const, value))

    def __eq__(self, other):
        return isinstance(other, Const) and self.value == other.value

class Name(Expr):
    def __init__(self, value):
        self.value = value

    def _reprargs(self):
        return (repr(self.value),)

    def __str__(self):
        return self.value

    def __hash__(self):
        return hash((Name, self.value))

    def __eq__(self, other):
        return isinstance(other, Name) and self.value == other.value

class Call(Expr):
    def __init__(self, fcn, *args):
        self.fcn = fcn
        self.args = args

    def _reprargs(self):
        return (repr(self.fcn),) + tuple(repr(x) for x in self.args)

    def __str__(self):
        return "{0}({1})".format(self.fcn, ", ".join(str(x) for x in self.args))

    def __hash__(self):
        return hash((Call, self.fcn, self.args))

    def __eq__(self, other):
        return isinstance(other, Call) and self.fcn == other.fcn and self.args == other.args

class UnaryOp(Call):
    def __init__(self, fcn, arg):
        super(UnaryOp, self).__init__(fcn, arg)

    def __str__(self):
        if isinstance(self.arg, BinOp):
            return self.fcn + "(" + str(self.arg) + ")"
        else:
            return self.fcn + str(self.arg)

class BinOp(Call):
    def __str__(self):
        return (" " + self.fcn + " ").join(("(" + str(x) + ")") if isinstance(x, BinOp) else str(x) for x in self.args)

class Relation(Expr):
    def __init__(self, cmp, arg, const):
        self.cmp = cmp
        self.arg = arg
        self.const = const

    def _reprargs(self):
        return (repr(self.cmp), repr(self.arg), repr(self.const))

    def __str__(self):
        return "{0} {1} {2}".format(str(self.arg), self.cmp, str(self.const))

    def __hash__(self):
        return hash((Relation, self.cmp, self.arg, self.const))

    def __eq__(self, other):
        return isinstance(other, Relation) and self.cmp == other.cmp and self.arg == other.arg and self.const == other.const

class Interval(Expr):
    def __init__(self, arg, low, high, lowclosed=True):
        self.arg = arg
        self.low = low
        self.high = high
        self.lowclosed = lowclosed

    def _reprargs(self):
        if self.lowclosed:
            return (repr(self.low), repr(self.high), repr(self.arg))
        else:
            return (repr(self.low), repr(self.high), repr(self.arg), "lowclosed=False")

    def __str__(self):
        if self.lowclosed:
            return "{0} <= {1} < {2}".format(str(self.low), str(self.arg), str(self.high))
        else:
            return "{0} < {1} <= {2}".format(str(self.low), str(self.arg), str(self.high))

    def __hash__(self):
        return hash((Interval, self.arg, self.low, self.high, self.lowclosed))

    def __eq__(self, other):
        return isinstance(other, Interval) and self.arg == other.arg and self.low == other.low and self.high == other.high and self.lowclosed == other.lowclosed

class Logical(Expr):
    def __init__(self, *args):
        self.args = args

    def _reprargs(self):
        return tuple(repr(x) for x in self.args)

    def __hash__(self):
        return hash((self.__class__,) + self.args)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.args == other.args

class And(Logical):
    def __str__(self):
        return " and ".format(str(x) for x in self.args)

class Or(Logical):
    def __str__(self):
        return " or ".format("(" + str(x) + ")" if isinstance(x, And) else str(x) for x in self.args)
