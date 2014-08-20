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

import time
import logging as l

from threading import Thread
from Queue import Queue

from dispatcher import Dispatcher
from bjob import Job

# ------------------------------------------------------------------------
class CopyDispatcher(Dispatcher):

    # --------------------------------------------------------------------
    def process(self, job):
        l.debug("Dispatching job '%s' for Copy" % job.full_name)

        bg_copies = []

        job.set_step(Job.JOB_STEP_COPYING)

        # spawn copy jobs
        for dest in job.dest:
            # don't try to reprocess DONE nor FAILED (permanently) destinations
            if dest.status != Job.COPY_STATUS_DONE and dest.status != Job.COPY_STATUS_FAILED:
                c = Copy(dest)
                c.start()
                if dest.bg:
                    bg_copies.append(c)
                else:
                    c.join()

        # wait for background copies to finish
        for bgc in bg_copies:
            bgc.join()

        # check dest statuses
        permanent_fail = False
        temporary_fail = False
        for dest in job.dest:
            if dest.status == Job.COPY_STATUS_FAILED:
                permanent_fail = True
            if dest.status == Job.COPY_STATUS_WARNING:
                temporary_fail = True

        # something to retry
        if temporary_fail:
            l.info("Putting job '%s' back to copy queue, will retry in %i seconds" % (job.full_name, job.copy_retry_min_sleep))
            self.queue(job, time.time() + job.copy_retry_min_sleep)
            job.set_status(Job.JOB_STATUS_WARNING)
        # nothing to retry
        else:
            # nothing failed permanently
            if not permanent_fail:
                l.debug("Putting job '%s' to post queue" % job.full_name)
                job.set_status(Job.JOB_STATUS_OK)
                self.dp_next.queue(job)
                job.remove_state()
            # something failed permanently
            else:
                l.error("Job '%s' failed permamently on copying" % job.full_name)
                job.set_status(Job.JOB_STATUS_FAILED)
                # write state, so we can continue with -c command line option
                job.write_state()


# ------------------------------------------------------------------------
class Copy(Thread):

    # --------------------------------------------------------------------
    def __init__(self, dest):
        l.debug("Initializing thread to copy job '%s' to destination '%s'" % (dest.job.full_name, dest.name))
        Thread.__init__(self, name="Copy")
        self.dest = dest

    # --------------------------------------------------------------------
    def run(self):

        l.info("Copying: %s -> %s (background: %s)" % (self.dest.job.full_name, self.dest.name, str(self.dest.bg)))

        try:
            self.dest.set_status(Job.COPY_STATUS_COPYING)
            self.dest.copy()
        except Exception, e:
            if self.dest.retries < 0:
                self.dest.set_status(Job.COPY_STATUS_FAILED)
                l.error("Copying %s -> %s failed (PERMANENTLY). Exception: %s" % (self.dest.job.full_name, self.dest.name, str(e)))
            else:
                self.dest.set_status(Job.COPY_STATUS_WARNING)
                l.warning("Copying %s -> %s failed (retries left: %i). Exception: %s" % (self.dest.job.full_name, self.dest.name, self.dest.retries, str(e)))
        else:
            self.dest.set_status(Job.COPY_STATUS_DONE)
            l.info("Copying: %s -> %s done" % (self.dest.job.full_name, self.dest.name))



# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
