#!/usr/bin/env python

# Copyright (c) 2018, DIANA-HEP
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

import numbers

import numpy

import histbook.axis

class Facet(object): pass

class OverlayFacet(Facet):
    def __init__(self, axis):
        self.axis = axis
    def __repr__(self):
        return ".overlay({0})".format(self.axis)

class StackFacet(Facet):
    def __init__(self, axis):
        self.axis = axis
    def __repr__(self):
        return ".stack({0})".format(self.axis)

class BesideFacet(Facet):
    def __init__(self, axis):
        self.axis = axis
    def __repr__(self):
        return ".beside({0})".format(self.axis)

class BelowFacet(Facet):
    def __init__(self, axis):
        self.axis = axis
    def __repr__(self):
        return ".below({0})".format(self.axis)

class StepFacet(Facet):
    def __init__(self, axis, profile):
        self.axis = axis
        self.profile = profile
    def __repr__(self):
        args = [repr(self.axis)]
        if self.profile is not None:
            args.append("profile={0}".format(self.profile))
        return ".step({0})".format("".join(args))
    @property
    def error(self):
        return False

class AreaFacet(Facet):
    def __init__(self, axis, profile):
        self.axis = axis
        self.profile = profile
    def __repr__(self):
        args = [repr(self.axis)]
        if self.profile is not None:
            args.append("profile={0}".format(self.profile))
        return ".area({0})".format("".join(args))
    @property
    def error(self):
        return False

class LineFacet(Facet):
    def __init__(self, axis, profile, error):
        self.axis = axis
        self.profile = profile
        self.error = error
    def __repr__(self):
        args = [repr(self.axis)]
        if self.profile is not None:
            args.append("profile={0}".format(self.profile))
        if self.error is not False:
            args.append("error={0}".format(self.error))
        return ".line({0})".format("".join(args))

class MarkerFacet(Facet):
    def __init__(self, axis, profile, error):
        self.axis = axis
        self.profile = profile
        self.error = error
    def __repr__(self):
        args = [repr(self.axis)]
        if self.profile is not None:
            args.append("profile={0}".format(self.profile))
        if self.error is not True:
            args.append("error={0}".format(self.error))
        return ".marker({0})".format("".join(args))

class FacetChain(object):
    def __init__(self, source, item):
        if isinstance(source, FacetChain):
            self._source = source._source
            self._chain = source._chain + (item,)
        else:
            self._source = source
            self._chain = (item,)

    def __repr__(self):
        return "".join(repr(x) for x in (self._source,) + self._chain)

    def __str__(self, indent="\n     ", paren=True):
        return ("(" if paren else "") + indent.join(repr(x) for x in (self._source,) + self._chain) + (")" if paren else "")

    def _singleaxis(self, axis):
        if axis is None:
            if len(self._source._group + self._source._fixed) == 1:
                axis, = self._source._group + self._source._fixed
            else:
                raise TypeError("histogram has more than one axis; one must be specified for plotting")
        return axis

    def _asaxis(self, axis):
        if axis is None:
            return None
        elif isinstance(axis, histbook.axis.Axis):
            return axis
        else:
            return self._source.axis[axis]

    def overlay(self, axis):
        if any(isinstance(x, OverlayFacet) for x in self._chain):
            raise TypeError("cannot overlay an overlay")
        return FacetChain(self, OverlayFacet(self._asaxis(axis)))

    def stack(self, axis):
        if any(isinstance(x, StackFacet) for x in self._chain):
            raise TypeError("cannot stack a stack")
        return FacetChain(self, StackFacet(self._asaxis(axis)))

    def beside(self, axis):
        if any(isinstance(x, BesideFacet) for x in self._chain):
            raise TypeError("cannot split plots beside each other that are already split with beside (can do beside and below)")
        return FacetChain(self, BesideFacet(self._asaxis(axis)))

    def below(self, axis):
        if any(isinstance(x, BelowFacet) for x in self._chain):
            raise TypeError("cannot split plots below each other that are already split with below (can do beside and below)")
        return FacetChain(self, BelowFacet(self._asaxis(axis)))
        
    def step(self, axis=None, profile=None):
        if any(isinstance(x, StackFacet) for x in self._chain):
            raise TypeError("only area can be stacked")
        return Plotable(self, StepFacet(self._asaxis(self._singleaxis(axis)), self._asaxis(profile)))

    def area(self, axis=None, profile=None):
        return Plotable(self, AreaFacet(self._asaxis(self._singleaxis(axis)), self._asaxis(profile)))

    def line(self, axis=None, profile=None, error=False):
        if any(isinstance(x, StackFacet) for x in self._chain):
            raise TypeError("only area can be stacked")
        if error and any(isinstance(x, (BesideFacet, BelowFacet)) for x in self._chain):
            raise NotImplementedError("error bars are currently incompatible with splitting beside or below (Vega-Lite bug?)")
        return Plotable(self, LineFacet(self._asaxis(self._singleaxis(axis)), self._asaxis(profile), error))

    def marker(self, axis=None, profile=None, error=True):
        if any(isinstance(x, StackFacet) for x in self._chain):
            raise TypeError("only area can be stacked")
        if error and any(isinstance(x, (BesideFacet, BelowFacet)) for x in self._chain):
            raise NotImplementedError("error bars are currently incompatible with splitting beside or below (Vega-Lite bug?)")
        return Plotable(self, MarkerFacet(self._asaxis(self._singleaxis(axis)), self._asaxis(profile), error))

class Plotable(object):
    def __init__(self, source, item):
        if isinstance(source, FacetChain):
            self._source = source._source
            self._chain = source._chain + (item,)
        else:
            self._source = source
            self._chain = (item,)

    def __repr__(self):
        return "".join(repr(x) for x in (self._source,) + self._chain)

    def __str__(self, indent="\n     ", paren=True):
        return ("(" if paren else "") + indent.join(repr(x) for x in (self._source,) + self._chain) + (")" if paren else "")

    @property
    def _last(self):
        return self._chain[-1]

    def _varname(self, i):
        return "d" + str(i)

    def _data(self, prefix=(), baseline=False):
        error = getattr(self._last, "error", False)
        profile = self._last.profile
        if profile is None:
            profiles = ()
        else:
            profiles = (profile,)

        projected = self._source.project(*(x.axis for x in self._chain))
        table = projected.table(*profiles, count=(profile is None), error=error, recarray=False)

        projectedorder = projected.axis
        lastj = projectedorder.index(self._last.axis)

        data = []
        domains = {}

        def recurse(j, content, row, base):
            if j == len(projectedorder):
                if base:
                    row = row + ((0.0, 0.0) if error else (0.0,))
                else:
                    row = row + tuple(content)
                data.append(dict(zip([self._varname(i) for i in range(len(row))], row)))

            else:
                axis = projectedorder[j]
                if isinstance(axis, histbook.axis.GroupAxis):
                    if axis not in domains:
                        domains[axis] = set()
                    domains[axis].update(axis.keys(content))

                for i, (n, x) in enumerate(axis.items(content)):
                    if isinstance(n, histbook.axis.Interval):
                        if j == lastj:
                            if numpy.isfinite(n.low) and numpy.isfinite(n.high):
                                if baseline and isinstance(axis, histbook.axis.bin) and n.low == axis.low:
                                    recurse(j + 1, x, row + (n.low,), True)
                                    recurse(j + 1, x, row + (n.low + 1e-10*(axis.high - axis.low),), base)
                                else:
                                    recurse(j + 1, x, row + (n.low,), base)

                                if baseline and isinstance(axis, histbook.axis.bin) and n.high == axis.high:
                                    recurse(j + 1, x, row + (n.high,), True)

                        else:
                            recurse(j + 1, x, row + (str(n),), base)

                    elif isinstance(n, (numbers.Integral, numpy.integer)):
                        recurse(j + 1, x, row + (n,), base)

                    else:
                        recurse(j + 1, x, row + (str(n),), base)

        recurse(0, table, prefix, False)
        return projectedorder, data, domains

    def vegalite(self):
        axis, data, domains = self._data(baseline=isinstance(self._last, (StepFacet, AreaFacet)))

        if isinstance(self._last, StepFacet):
            mark = {"type": "line", "interpolate": "step-before"}
        elif isinstance(self._last, AreaFacet):
            mark = {"type": "area", "interpolate": "step-before"}
        elif isinstance(self._last, LineFacet):
            mark = {"type": "line"}
        elif isinstance(self._last, MarkerFacet):
            mark = {"type": "point"}
        else:
            raise AssertionError(self._last)

        xtitle = self._last.axis.expr
        if self._last.profile is None:
            ytitle = "entries per bin"
        else:
            ytitle = self._last.profile.expr

        transform = []
        def makeorder(i, var, values):
            if len(values) == 1:
                return "if(datum.{0} === {1}, {2}, {3})".format(var, repr(values[0]), i, i + 1)
            elif len(values) > 1:
                return "if(datum.{0} === {1}, {2}, {3})".format(var, repr(values[0]), i, makeorder(i + 1, var, values[1:]))
            else:
                raise AssertionError(values)

        encoding = {"x": {"field": self._varname(axis.index(self._last.axis)), "type": "quantitative", "scale": {"zero": False}, "axis": {"title": xtitle}},
                    "y": {"field": self._varname(len(axis)), "type": "quantitative", "axis": {"title": ytitle}}}
        for facet in self._chain[:-1]:
            if isinstance(facet, OverlayFacet):
                overlayorder = [str(x) for x in sorted(domains[facet.axis])]
                encoding["color"] = {"field": self._varname(axis.index(facet.axis)), "type": "nominal", "legend": {"title": facet.axis.expr}, "scale": {"domain": overlayorder}}

            elif isinstance(facet, StackFacet):
                stackorder = [str(x) for x in sorted(domains[facet.axis])]
                encoding["color"] = {"field": self._varname(axis.index(facet.axis)), "type": "nominal", "legend": {"title": facet.axis.expr}, "scale": {"domain": list(reversed(stackorder))}}
                encoding["y"]["aggregate"] = "sum"
                encoding["order"] = {"field": "stackorder", "type": "nominal"}
                transform.append({"calculate": makeorder(0, self._varname(axis.index(facet.axis)), stackorder), "as": "stackorder"})

            elif isinstance(facet, BesideFacet):
                # FIXME: sorting doesn't work???
                encoding["column"] = {"field": self._varname(axis.index(facet.axis)), "type": "nominal", "header": {"title": facet.axis.expr}}

            elif isinstance(facet, BelowFacet):
                # FIXME: sorting doesn't work???
                encoding["row"] = {"field": self._varname(axis.index(facet.axis)), "type": "nominal", "header": {"title": facet.axis.expr}}

            else:
                raise AssertionError(facet)

        if self._last.error:
            encoding2 = {"x": {"field": self._varname(axis.index(self._last.axis)), "type": "quantitative"},
                         "y": {"field": "error-down", "type": "quantitative"},
                         "y2": {"field": "error-up", "type": "quantitative"}}
            return {"$schema": "https://vega.github.io/schema/vega-lite/v2.json",
                    "data": {"values": data},
                    "layer": [
                        {"mark": mark, "encoding": encoding},
                        {"mark": "rule", "encoding": encoding2,
                         "transform": [
                             {"calculate": "datum.{0} - datum.{1}".format(self._varname(len(axis)), self._varname(len(axis) + 1)), "as": "error-down"},
                             {"calculate": "datum.{0} + datum.{1}".format(self._varname(len(axis)), self._varname(len(axis) + 1)), "as": "error-up"}]
                             + transform
                         }]}

        else:
            return {"$schema": "https://vega.github.io/schema/vega-lite/v2.json",
                    "data": {"values": data},
                    "mark": mark,
                    "encoding": encoding,
                    "transform": transform}

    def to(self, fcn):
        return fcn(self.vegalite())

class Combination(object):
    def __init__(self, *plotables):
        self._plotables = plotables

    def __repr__(self):
        return "{0}({1})".format(self.__class__.__name__, ", ".join(repr(x) for x in self._plotables))

    def __str__(self, indent="\n    ", paren=False):
        return "{0}({1})".format(self.__class__.__name__, "".join(indent + x.__str__(indent + "    ", False) for x in self._plotables))

    def to(self, fcn):
        return fcn(self.vegalite())

class overlay(Combination):
    def vegalite(self):
        raise NotImplementedError

class beside(Combination):
    def vegalite(self):
        raise NotImplementedError

class below(Combination):
    def vegalite(self):
        raise NotImplementedError