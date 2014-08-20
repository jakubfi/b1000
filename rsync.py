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

import os
import os.path
import re
import subprocess
import logging as l
import tempfile

from butils import run_and_log

# ------------------------------------------------------------------------
class Rsync:

    # --------------------------------------------------------------------
    def __init__(self, name, src, dst, exclude, timeout=20):
        self.rsync_cmd = "rsync"
        self.name = name
        self.defopts = set(["a", "z"])

        self.src = src
        self.dst = dst
        self.exclude = ""
        self.timeout = "--timeout=%i --contimeout=%i" % (timeout, timeout)
        if exclude:
            for e in exclude.split(" "):
                if e:
                    self.exclude += " --exclude '%s' " % e

        self.ver_rsync = ""
        self.ver_proto = 0

        self.verbosity = 0
        self.opts = self.defopts

        # doesn't work in 2.5
        #self.__check_version()

    # --------------------------------------------------------------------
    def __check_version(self):
        try:
            output = subprocess.check_output([self.rsync_cmd, "--version"])
        except Exception, e:
            raise RuntimeError("Can't run rsync command '%s'. Exception: %s" % (self.rsync_cmd, str(e)))
        r = re.search("rsync +version +([.0-9]+) +protocol +version +([0-9]+)", output)
        if not r or len(r.groups()) != 2:
            raise LookupError("Can't parse rsync version string")
        self.ver_rsync, self.ver_proto = r.groups()

    # --------------------------------------------------------------------
    def get_version(self):
        return self.ver_rsync, self.ver_proto

    # --------------------------------------------------------------------
    def set_opts(self, opts=None):
        if opts:
            self.opts = set(opts)
        else:
            self.opts.clear()

    # --------------------------------------------------------------------
    def add_opts(self, opts):
        self.opts |= set(opts)

    # --------------------------------------------------------------------
    def remove_opts(self, opts):
        self.opts -= set(opts)

    # --------------------------------------------------------------------
    def get_opts(self):
        return self.opts

    # --------------------------------------------------------------------
    def set_verbosity(self, v):
        if v < 0:
            v = 0
        if v > 3:
            v = 3
        self.verbosity = v

    # --------------------------------------------------------------------
    def __prep_opts(self):
        po = ""
        for o in self.opts:
            if len(o) == 1:
                po += " -%s" % o
            else:
                po += " --%s" % o

        if self.verbosity:
            po += " -vvvvv"[:self.verbosity+2]

        return po
                
    # --------------------------------------------------------------------
    def mkdir(self, dest):

        # this is another not-so-nasty hack to "make dirs" on server side
        if dest.startswith("rsync://"):
            try:
                chunks = re.search("(rsync://[^/]+/[^/]+)/(.*)", dest)
                root = chunks.group(1)
                subdir = chunks.group(2)
            except Exception, e:
                l.debug("No subdirectories to create on remote '%s'" % (dest))
                return

            tmpdir = tempfile.mkdtemp(prefix="b1000-rsync-mkdir-")
            the_dir = "%s/%s" % (tmpdir, subdir)
            os.makedirs(the_dir)

            cmd = "%s -arq %s %s/* %s" % (self.rsync_cmd, self.timeout, tmpdir, root)

            l.debug("Creating subdirectories '%s' on '%s'" % (subdir, root))

            run_and_log(cmd)
            os.removedirs(the_dir)

        # locally, just mkdirs()
        elif dest.startswith("/"):
            if not os.path.isdir(dest):
                l.debug("Creating local subdirectories: '%s'" % dest)
                os.makedirs(dest)
            else:
                l.debug("Local directory '%s' exists, no need to create one" % dest)

        # we don't know how to handle other types
        else:
            raise OSError("Don't know how to make proper subdirs for destination: %s" % dest)

    # --------------------------------------------------------------------
    def run(self):

        # first create necessary directory structure on remote server
        try:
            self.mkdir(self.dst)
        except Exception, e:
            raise OSError("Could not create remote directory '%s'. Exception: %s" % (self.dst, str(e)))

        # start rsync process
        try:
            cmd = "%s %s %s %s %s %s" % (self.rsync_cmd, self.exclude, self.timeout, self.__prep_opts(), self.src, self.dst)
            l.debug("Running rsync command: %s" % cmd)
            run_and_log(cmd, "rsync " + self.name)
        except Exception, e:
            raise OSError("Exception while running rsync: %s" % str(e))



# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
