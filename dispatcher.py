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
import Queue
from threading import Thread

# ------------------------------------------------------------------------
class Dispatcher(Thread):

    # --------------------------------------------------------------------
    def __init__(self, dp_name, dp_next):
        l.debug("Initializing %s Dispatcher" % dp_name)
        Thread.__init__(self, name=dp_name)
        self.name = dp_name
        self.q = Queue.Queue()
        self.dp_next = dp_next
        self.fin = False

    # --------------------------------------------------------------------
    def finish(self):
        self.fin = True

    # --------------------------------------------------------------------
    def queue(self, o, when=None):
        self.q.put((o, when))

    # --------------------------------------------------------------------
    def process(self, i):
        raise NotImplementedError("Dispatcher.process() method not implemented")

    # --------------------------------------------------------------------
    def run(self):
        l.debug("Running %s Dispatcher" % self.name)

        while not (self.fin and self.q.empty()):
            try:
                (i, when) = self.q.get(True, 0.3)
                now = time.time()
                # is it time for this?
                if (when is not None) and (when > now):
                    self.queue(i, when)
                    time.sleep(0.5)
                    continue
            except Queue.Empty:
                continue

            try:
                self.process(i)
            except Exception, e:
                l.error("Exception while processing %s: %s" % (str(i), str(e)))

        if self.dp_next is not None:
            self.dp_next.finish()

        l.debug("Exiting %s Dispatcher loop" % self.name)


# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
