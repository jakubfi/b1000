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
from bjob import Job

# ------------------------------------------------------------------------
class PostDispatcher(Dispatcher):

    # --------------------------------------------------------------------
    def process(self, job):
        if job.post:
            l.debug("Dispatching job '%s' for Post" % job.full_name)

            job.set_step(Job.JOB_STEP_POST)

            p = Post(job)
            p.start()
            p.join()

            if p.failed:
                job.set_status(Job.JOB_STATUS_FAILED)
            else:
                job.set_step(Job.JOB_STEP_DONE)
        else:
            l.debug("No post script for job '%s'" % job.full_name)
            job.set_step(Job.JOB_STEP_DONE)

        l.debug("Running job.outro()")
        try:
            job.outro()
        except Exception, e:
            job.set_status(Job.JOB_STATUS_FAILED)
            l.error("job.outro() failed. Exception: %s" % str(e))
            return


# ------------------------------------------------------------------------
class Post(Thread):

    # --------------------------------------------------------------------
    def __init__(self, job):
        l.debug("Initializing thread to postprocess job '%s'" % job.full_name)
        Thread.__init__(self, name="Post")

        self.job = job
        self.failed = True

    # --------------------------------------------------------------------
    def run(self):
        l.info("Running post script '%s' for job '%s'" % (self.job.post, self.job.full_name))

        try:
            run_and_log(self.job.post)
        except Exception, e:
            self.failed = True
            l.warning("Post script '%s' failed. Exception: %s" % (self.job.post, str(e)))
        else:
            self.failed = False
            l.info("Post script for job '%s' done" % (self.job.full_name))
        


# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
