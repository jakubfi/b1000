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

from threading import Thread
from Queue import Queue
from dispatcher import Dispatcher
from butils import run_and_log
from bjob import Job, job_generator, NoReportException

# ------------------------------------------------------------------------
class PreDispatcher(Dispatcher):

    # --------------------------------------------------------------------
    def process(self, j):
        self.cfg, self.job_name, self.instance = j

        try:
            job = job_generator(self.cfg, self.job_name, self.instance)
        except NoReportException, e:
            l.warning("Could not create pull job '%s' instance '%s'. Exception: %s" % (self.job_name, self.instance, e))
            return
        except Exception, e:
            l.error("Could not create job '%s' (instance '%s'). Exception: %s" % (self.job_name, self.instance, str(e)))
            return

        l.debug("Running job.intro()")
        try:
            job.intro()
        except Exception, e:
            job.set_status(Job.JOB_STATUS_FAILED)
            l.error("job.intro() failed. Exception: %s" % str(e))
            return

        if job.pre:
            l.debug("Dispatching job '%s' for Pre" % job.full_name)

            job.set_step(Job.JOB_STEP_PRE)

            p = Pre(job)
            p.start()
            p.join()

            if p.failed:
                job.set_status(Job.JOB_STATUS_FAILED)
            else:
                l.debug("Putting job '%s' to copy queue" % job.full_name)
                self.dp_next.queue(job)
            
        else:
            l.debug("No pre for job '%s', putting to copy queue" % job.full_name)
            self.dp_next.queue(job)



# ------------------------------------------------------------------------
class Pre(Thread):

    # --------------------------------------------------------------------
    def __init__(self, job):
        l.debug("Initializing thread to preprocess job '%s'" % job.full_name)
        Thread.__init__(self, name="Pre")

        self.job = job
        self.failed = True

    # --------------------------------------------------------------------
    def run(self):
        l.info("Running pre script '%s' for job '%s'" % (self.job.pre, self.job.full_name))

        try:
            run_and_log(self.job.pre)
        except Exception, e:
            self.failed = True
            l.error("Pre script '%s' failed. Exception: %s" % (self.job.post, str(e)))
        else:
            self.failed = False
            l.info("Pre script for job '%s' done" % (self.job.full_name))

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
