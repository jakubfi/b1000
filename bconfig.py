# Copyright (c) 2012 Jakub Filipowicz <jakubf@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import re
import ConfigParser
import subprocess

# ------------------------------------------------------------------------
class Config:

    # --------------------------------------------------------------------
    def __init__(self, cfgfile):
        self.jobs = []
        self.destinations = []
        self.reports = []
        self.pulls = []

        self.cfg = ConfigParser.RawConfigParser()

        f_cfg = open(cfgfile)
        self.cfg.readfp(f_cfg)
        f_cfg.close()

        self.__parse_sections()

    # --------------------------------------------------------------------
    def __parse_sections(self):
        for s in self.cfg.sections():
            if not s.startswith("job:") and not s.startswith("report:") and not s.startswith("dest:") and not s == "global":
                raise SyntaxError("Section '%s' is not allowed" % s)

            if s.startswith("job:"):
                self.jobs.append([s, ''])

    # --------------------------------------------------------------------
    def dump(self):
        for s in self.cfg.sections():
            print "\n[" + s + "]"
            for o in self.cfg.options(s):
                print "   " + o + " = " + self.cfg.get(s, o)

    # --------------------------------------------------------------------
    def set(self, section, option, value):
        self.cfg.set(section, option, value)

    # --------------------------------------------------------------------
    def has_section(self, section):
        return self.cfg.has_section(section)

    # --------------------------------------------------------------------
    def has_option(self, section, option):
        return self.cfg.has_option(section, option)

    # --------------------------------------------------------------------
    def options(self, section):
        return self.cfg.options(section)

    # --------------------------------------------------------------------
    def get(self, section, option):

        value = self.cfg.get(section, option)
        variables = re.findall(r'\$[a-zA-Z][a-zA-Z0-9_]*', value)

        # try to substitute (recursively) each variable
        for v in variables:
            # search localy
            try:
                subst = self.get(section, v[1:])
            except:
                # search globaly
                try:
                    subst = self.get('global', v[1:])
                except:
                    raise ValueError("Undefined variable: %s" % v)

            value = value.replace(v, subst)

        return value

    # --------------------------------------------------------------------
    def get_def(self, section, option, default):
        try:
            value = self.get(section, option)
        except:
            value = default
        return value

    # --------------------------------------------------------------------
    def get_exec(self, section, option):

        value = self.get(section, option)

        if value.startswith("!"):
            value = subprocess.check_output(value[1:], shell=True)

        return value

    # --------------------------------------------------------------------
    def get_exec_def(self, section, option, default):
        try:
            value = self.get_exec(section, option)
        except:
            value = default
        return value

    # --------------------------------------------------------------------
    def validate(self, section, required, allowed):
        for r in required:
            if not self.cfg.has_option(section, r):
                raise SyntaxError("Required parameter '%s' missing in section '%s'" % (r, section))
        for p in self.cfg.options(section):
            if (p not in allowed) and (p not in required):
                raise SyntaxError("Parameter '%s' not allowed for section '%s'" % (p, section))

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
