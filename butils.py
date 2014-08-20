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
import logging as l
import subprocess

# --------------------------------------------------------------------
def run_and_log(cmd,name=None, lvl=l.DEBUG):

    if name is None:
        name = cmd.split(" ")[0].split("/")[-1]

    # start process
    process = subprocess.Popen(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    fd = process.stdout

    # process and log output
    while not fd.closed:
        line = ""
        try:
            line = fd.readline()
        except:
            pass

        if line:
            l.log(lvl, "[%s] %s" % (name, line.rstrip("\n")))
        else:
            try:
                fd.close()
            except:
                pass

    process.wait()
    ret = process.poll()

    if ret < 0:
        raise OSError("Process terminated by signal: %i" % -ret)
    elif ret > 0:
        raise OSError("Process exited with code: %i" % ret)
    else:
        pass

# --------------------------------------------------------------------
def get_lock(name):
    if os.access(name, os.F_OK):
        raise OSError("Could not get lock. File %s exists" % name)
    else:
        f = open(name, "w")
        f.write("%s" % os.getpid())
        f.close()

# --------------------------------------------------------------------
def release_lock(name):
    os.remove(name)

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
