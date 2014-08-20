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

import logging as l

import time
import os
import os.path
import glob

from rsync import Rsync

# ------------------------------------------------------------------------
def dest_generator(job, cfg, name, bg):
    dest_type = cfg.get("dest:" + name, 'type')
    if dest_type == 'active':
        return DestRsync(job, cfg, name, bg)
    elif dest_type == 'passive':
        return DestPassive(job, cfg, name, bg)
    else:
        raise SyntaxError("Unknown destination type '%s' for destination '%s'" % (dest_type, name))

# ------------------------------------------------------------------------
class Dest:

    params_required = ['type']
    params_allowed = []

    # --------------------------------------------------------------------
    def __init__(self, job, cfg, name, bg):
        from bjob import Job
        self.status = Job.COPY_STATUS_INIT
        self.job = job
        self.name = name
        self.sname = "dest:" + name
        self.bg = bg
        self.cfg = cfg
        self.type = cfg.get(self.sname, "type")
        self.cfg.validate(self.sname, self.params_required, self.params_allowed)
 
    # --------------------------------------------------------------------
    def set_status(self, status):
        self.status = status
        for r in self.job.report:
            r.update()

    # --------------------------------------------------------------------
    def copy(self):
        raise NotImplementedError


# ------------------------------------------------------------------------
class DestRsync(Dest):

    params_required = ['type', 'path']
    params_allowed = ['verbosity', 'exclude']

    # --------------------------------------------------------------------
    def __init__(self, job, cfg, name, bg):
        l.debug("Adding rsync destination '%s' (background: %s) to job '%s'" % (name, str(bg), job.real_name))

        Dest.__init__(self, job, cfg, name, bg)

        self.exclude = cfg.get_def(self.sname, "exclude", "")
        self.verbosity = int(cfg.get_def(self.sname, "verbosity", "1"))

        self.path = self.__prepare_path()

        self.retries = int(cfg.get_def("global", "copy_retries", '3'))
        self.retry_sleep = int(cfg.get_def("global", "copy_retries", '60'))

    # --------------------------------------------------------------------
    def __prepare_path(self):
        path = self.cfg.get(self.sname, "path")

        if not path.endswith("/"):
            path += "/"

        path += self.job.get_job_path()

        return path

    # --------------------------------------------------------------------
    def copy(self):
        excludes = self.job.exclude + " " + self.exclude
        l.debug("Copying '%s' to '%s' on destination '%s' excluding: '%s'" % (self.job.include, self.path, self.name, excludes))
        self.rsync = Rsync(self.name, self.job.include, self.path, excludes)
        self.rsync.set_verbosity(self.verbosity)
        self.retries -= 1
        self.rsync.run()


# ------------------------------------------------------------------------
class DestPassive(Dest):

    params_required = ['type', 'host', 'timeout']
    params_allowed = []

    # --------------------------------------------------------------------
    def __init__(self, job, cfg, name, bg):
        l.debug("Adding passive destination '%s' to job '%s'" % (name, job.real_name))

        if not job.report_dir:
            raise SyntaxError("'passive' destination needs a job with 'file' report configured")

        Dest.__init__(self, job, cfg, name, bg)

        self.host = cfg.get(self.sname, "host")
        self.timeout = int(cfg.get("dest:" + name, "timeout"))
        self.retries = -1 # we don't retry destinations that are pulled
        self.path = 'pull://%s' % self.host # pulling side decides where to store data, we note here who should pull

    # --------------------------------------------------------------------
    def copy(self):

        l.info("Waiting for host '%s' to pull job's data from destination '%s'" % (self.host, self.name))

        start_time = time.strftime("%Y-%m-%d-%H-%M-%S", self.job.start_time)
        status_files = self.job.report_dir + "/" + self.job.real_name + "-" + self.job.instance + "-" + start_time + ".b1k." + self.host + ".*"
        
        l.debug("Waiting for files matching '%s' (with timeout of %i seconds)" % (status_files, self.timeout))
        wait_started = time.time()

        while True:

            files = glob.glob(status_files)
            if files:
                for f in files:

                    # remove the status file, we don't need it anymore
                    try:
                        os.remove(f)
                    except Exception, e:
                        l.warning("Could not remove status file '%s'" % f)

                    # check the remote status
                    if f.endswith(".error"):
                        raise RuntimeError("Remote job returned 'ERROR'")
                    elif f.endswith(".done"):
                        l.debug("Remote job returned 'DONE'")
                    else:
                        l.warning("Remote job wrote file with unknown status: %s" % f)
                break

            if time.time() - wait_started > self.timeout:
                raise RuntimeError("Timeout while waiting for host '%s' to pull data from destination '%s'" % (self.host, self.name))
            time.sleep(1)




# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
