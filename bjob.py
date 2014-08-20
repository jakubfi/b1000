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
import re
import time
import random
import platform
import logging as l
import pickle
import tempfile
import shutil
import ConfigParser
import glob

from rsync import Rsync
from breport import ReportMysql, ReportFile, Values
from bdest import Dest, dest_generator
from butils import get_lock, release_lock

class NoReportException(BaseException):
    pass

# --------------------------------------------------------------------
def pull_report(report_source):
    l.debug("Pulling remote report '%s'" % report_source)
    tmpdir = tempfile.mkdtemp(prefix="b1000-remote-report-")

    try:
        rsync = Rsync("remote_report", report_source, tmpdir, "")
        rsync.run()

        reports = os.listdir(tmpdir)

        report = ConfigParser.RawConfigParser()
        report.readfp(open(tmpdir + "/" + reports[0]))
    except Exception, e:
        raise NoReportException("Could not read report file '%s'. Exception: %s" % (report_source, str(e)))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return report, reports[0]

# ------------------------------------------------------------------------
def job_generator(cfg, name, instance):
    jdirection = cfg.get(name, 'direction')
    if jdirection == 'passive':
        return JobPassive(cfg, name, instance)
    if jdirection == 'push':
        return Job(cfg, name, instance)
    elif jdirection == 'pull':
        report_source = cfg.get(name, "report_source")
        real_name = re.sub("job:", "", name)
        report, report_file = pull_report(report_source + "/" + real_name + "-" + instance + "-" + "*.b1k")

        my_dest_section = None
        for s in report.sections():
            try:
                if report.get(s, "path") == "pull://" + platform.node():
                    my_dest_section = s
            except:
                pass

        if my_dest_section is None:
            raise RuntimeError("Job reported in file '%s' is not for host '%s'" % (report_file, platform.node()))

        return JobPull(cfg, name, instance, report, report_file, my_dest_section)
    else:
        raise SyntaxError("Unknown job direction '%s' for job '%s'" % (jdirection, name))



# ------------------------------------------------------------------------
class Job:

    # MySQL enums for all steps and states

    JOB_STEP_INIT = "INIT"
    JOB_STEP_PRE = "PRE"
    JOB_STEP_COPYING = "COPYING"
    JOB_STEP_POST = "POST"
    JOB_STEP_DONE = "DONE"

    JOB_STATUS_OK = "OK"
    JOB_STATUS_WARNING = "WARNING"
    JOB_STATUS_FAILED = "FAILED"

    COPY_STATUS_INIT = "INIT"
    COPY_STATUS_COPYING = "COPYING"
    COPY_STATUS_DONE = "DONE"
    COPY_STATUS_WARNING = "WARNING"
    COPY_STATUS_FAILED = "FAILED"

    params_required = ['type', 'direction', 'dest', 'report', 'include']
    params_allowed = ['exclude', 'pre', 'post', 'instances', 'data_age', 'master_host', 'master_instance']

    # --------------------------------------------------------------------
    def __init__(self, cfg, name, instance):

        self.name = name

        self.start_time = time.localtime()

        self.real_name = re.sub("job:", "", self.name)

        cfg.validate(self.name, self.params_required, self.params_allowed)

        cfg.set(name, "name", self.real_name)

        if instance:
            self.full_name = "%s/%s" % (self.real_name, instance)
        else:
            self.full_name = self.real_name

        l.debug("Creating job: %s" % self.full_name)

        self.step = Job.JOB_STEP_INIT
        self.status = Job.JOB_STATUS_OK
        self.report = []
        self.dest = []

        # run-time parameter: host name
        self.host = platform.node()
        cfg.set(name, "host", self.host)

        # run-time parameter: instance name
        cfg.set(name, "instance", instance)
        self.instance = instance

        # run-time parameter: start_time
        start_time = time.strftime("%Y-%m-%d-%H-%M-%S", self.start_time)
        cfg.set(name, "start_time", start_time)

        self.direction = cfg.get(self.name, "direction")
        # TODO: this is ugly, this should be done with a proper base class
        if self.direction != 'passive':
            self.type = cfg.get(self.name, "type")
            if self.type != 'sync' and self.type != 'full':
                raise SyntaxError("Unknown job type '%s'" % self.type)
        self.include = cfg.get_def(self.name, "include", "__none__")

        self.master_host = cfg.get_exec_def(self.name, "master_host", '')
        self.master_instance = cfg.get_exec_def(self.name, "master_instance", '')

        self.exclude = cfg.get_def(self.name, "exclude", '')
        self.data_age = cfg.get_exec_def(self.name, "data_age", '0')
        self.pre = cfg.get_def(self.name, "pre", '')
        self.post = cfg.get_def(self.name, "post", '')

        self.copy_retry_min_sleep = int(cfg.get_def('global', "copy_retry_min_sleep", '60'))
        self.status_dir = cfg.get('global', "status_dir")
        self.report_dir = "" # this gets filled when reportFile is registered
        self.stat_filename = self.status_dir + "/" + self.host + "-" + self.real_name + "-" + self.instance + "-" + start_time + ".b1ks"

        self.lockfile = self.status_dir + "/b1000_job_" + self.real_name + ".lock"

        self.__parse_report(cfg)
        self.__parse_dest(cfg)

    # --------------------------------------------------------------------
    def get_report_data(self):
        jrd = Values()

        jrd.jdirection = self.direction
        jrd.name = self.real_name
        jrd.host = self.host
        jrd.instance = self.instance
        jrd.master_host = self.master_host
        jrd.master_instance = self.master_instance
        jrd.start_time = self.start_time
        jrd.step = self.step
        jrd.status = self.status
        jrd.data_age = self.data_age
        jrd.destinations = []

        for d in self.dest:
            drd = Values()

            drd.name = d.name
            drd.dtype = d.type
            drd.path = d.path
            drd.status = d.status
            jrd.destinations.append(drd)

        return jrd

    # --------------------------------------------------------------------
    def __parse_dest(self, cfg):

        dest = cfg.get(self.name, "dest")
        dest_list = re.findall("([a-zA-Z][-_&/a-zA-Z0-9]*)", dest)

        for d in dest_list:

            # handle background destination
            bg = False
            if d.endswith('&'):
                bg = True
                d = d.replace('&', '')

            d_l = []

            # handle randomization
            if d.find('/') != -1:
                d_l = d.split('/')
                random.shuffle(d_l)
            else:
                d_l.append(d)

            for i in d_l:
                try:
                    self.dest.append(dest_generator(self, cfg, i, bg))
                except Exception, e:
                    l.error("Cannot add destionation '%s' to job '%s'. Exception: %s" % (i, self.real_name, str(e)))

        if len(self.dest) < 1:
            raise RuntimeError("No valid destinations for job '%s'" % (self.real_name))


    # --------------------------------------------------------------------
    def __parse_report(self, cfg):
        report = cfg.get(self.name, "report")
        report_list = re.findall("([a-zA-Z][-_a-zA-Z0-9]*)", report)

        for r in report_list:
            try:
                rtype = cfg.get("report:" + r, "type")
                if rtype == "mysql":
                    report = ReportMysql(self, cfg, r)
                    self.report.append(report)
                    report.update()
                elif rtype == "file":
                    report = ReportFile(self, cfg, r)
                    self.report.append(report)
                    report.update()
                else:
                    raise SyntaxError("Unknown report type: %s" % rtype)
            except Exception, e:
                l.error("Cannot add report '%s' to job '%s'. Exception: %s" % (r, self.real_name, str(e)))

    # --------------------------------------------------------------------
    def set_state(self, step, status):
        if step is not None:
            self.step = step
        if status is not None:
            self.status = status
        for r in self.report:
            r.update()

    # --------------------------------------------------------------------
    def set_step(self, step):
        self.set_state(step, None)

    # --------------------------------------------------------------------
    def set_status(self, status):
        self.set_state(None, status)

    # --------------------------------------------------------------------
    def get_job_path(self):

        path = ""

        path += self.real_name + "/"

        if self.type == 'full':
            date = time.strftime("%Y-%m-%d-%A", self.start_time)
            path += date + "/"

        path += self.host
        
        if self.instance:
            path += "-" + self.instance
        if self.master_host:
            path += "-" + self.master_host
        if self.master_instance:
            path += "-" + self.master_instance

        if self.type == "full":
            ts = time.strftime("%Y-%m-%d-%a-%H:%M:%S", self.start_time)
            path += "-" + ts

        path += "/"

        return path

    # --------------------------------------------------------------------
    def write_state(self):
        l.debug("Writing job state: %s" % self.stat_filename)
        try:
            f = open(self.stat_filename, "wb")
            pickle.dump(self, f)
            f.close()
        except Exception, e:
            l.warning("Could not write job '%s' state, you won't be able to continue failed copies. Exception: %s" % (self.real_name, str(e)))

    # --------------------------------------------------------------------
    def remove_state(self):
        try:
            os.remove(self.stat_filename)
        except Exception, e:
            pass

    # --------------------------------------------------------------------
    def intro(self):
        pass

    # --------------------------------------------------------------------
    def outro(self):
        pass


# ------------------------------------------------------------------------
class JobPassive(Job):

    params_required = ['direction', 'dest', 'report']
    params_allowed = ['pre', 'post']

    # --------------------------------------------------------------------
    def __init__(self, cfg, name, instance):
        Job.__init__(self, cfg, name, instance)
        start_time = time.strftime("%Y-%m-%d-%H-%M-%S", self.start_time)
        self.report_file  = self.report_dir + "/" + self.real_name + "-" + self.instance + "-" + start_time + ".b1k"
        self.__cleanup()

    # --------------------------------------------------------------------
    def __cleanup(self):
        # cleanup things that remote (active) pull job has written after
        # we've given up last time (if any)
        stale_statuses = self.report_dir + "/" + self.real_name + "-" + self.instance + "-*.b1k.*"
        trash_files = glob.glob(stale_statuses)
        if trash_files:
            for t in trash_files:
                r = re.sub("\.b1k\..*", ".b1k", t)
                l.debug("[CLEANUP] removing '%s'" % t)
                l.debug("[CLEANUP] removing '%s'" % r)
                try:
                    os.remove(t)
                except:
                    pass
                try:
                    os.remove(r)
                except:
                    pass

    # --------------------------------------------------------------------
    def intro(self):
        Job.intro(self)

    # --------------------------------------------------------------------
    def outro(self):
        l.debug("Removing report file '%s'" % self.report_file)
        os.remove(self.report_file)
        Job.outro(self)


# ------------------------------------------------------------------------
class JobPull(Job):

    params_required = ['type', 'direction', 'dest', 'report', 'include', 'report_source', 'report_poll_wait', 'report_poll_retries']
    params_allowed = ['exclude']

    # --------------------------------------------------------------------
    def __init__(self, cfg, name, instance, remote_report, remote_report_file, dest_section):

        self.report_source = cfg.get(name, "report_source")
        self.report_poll_wait = int(cfg.get(name, "report_poll_wait"))
        self.report_poll_retries = int(cfg.get(name, "report_poll_retries"))
        self.remote_report = remote_report
        self.remote_report_file = remote_report_file
        self.dest_section = dest_section

        Job.__init__(self, cfg, name, instance)

        if len(self.dest) > 1:
            raise SyntaxError("'Pull' job can have only one destination defined")

        l.debug("Report '%s' bound to pull job: '%s'" % (self.remote_report_file, self.real_name))

        for r in self.report:
            r.update()


    # --------------------------------------------------------------------
    def get_report_data(self):
        jrd = Values()

        js = "jobstatus:" + self.real_name

        try:
            self.remote_report, self.remote_report_file = pull_report(self.report_source + "/" + self.remote_report_file)
        except Exception, e:
            l.warning("Could not fetch remote report. Monitoring data may be inaccurate. Exception: %s" % str(e))

        jrd.jdirection = self.remote_report.get(js, "direction")
        jrd.name = self.remote_report.get(js, "name")
        jrd.host = self.remote_report.get(js, "host")
        jrd.instance = self.remote_report.get(js, "instance")
        jrd.master_host = self.remote_report.get(js, "master_host")
        jrd.master_instance = self.remote_report.get(js, "master_instance")
        jrd.start_time = time.strptime(self.remote_report.get(js, "start_time"), "%Y-%m-%d %H:%M:%S")
        jrd.step = self.remote_report.get(js, "step")
        if self.status != Job.JOB_STATUS_OK:
            jrd.status = self.status
        else:
            jrd.status = self.remote_report.get(js, "status")
        jrd.data_age = self.remote_report.get(js, "data_age")

        jrd.destinations = []

        drd = Values()
        drd.name = re.sub("pull://", "", self.dest_section)
        drd.dtype = self.remote_report.get(self.dest_section, "type")
        drd.path = self.remote_report.get(self.dest_section, "path")
        drd.status = self.remote_report.get(self.dest_section, "status")

        jrd.destinations.append(drd)

        return jrd

    # --------------------------------------------------------------------
    def __notify_remote(self, status):
        l.debug("Sending notification '%s' to remote '%s'" % (status, self.report_source))

        tmpdir = tempfile.mkdtemp(prefix="b1000-remote-notify-")
        status_file = tmpdir + "/" + self.remote_report_file + "." + platform.node() + "." + status

        # prepare message file
        open(status_file, "w").close()

        # rsync messge file
        try:
            rsync = Rsync("remote_notify", status_file, self.report_source, "")
            rsync.run()
        except:
            raise
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # --------------------------------------------------------------------
    def set_state(self, step, status):
        # do the usual work
        Job.set_state(self, step, status)
        # but also notify remote if something has gone wrong
        if self.status == Job.JOB_STATUS_FAILED:
            self.__notify_remote("error")

    # --------------------------------------------------------------------
    def intro(self):
        Job.intro(self)

        retries = self.report_poll_retries
        l.info("Polling remote job every %i seconds waiting for it to enter '%s' state (%i retries total)" % (self.report_poll_wait, Job.JOB_STEP_COPYING, retries))

        # waiting for remote passive job to enter 'COPYING' state (means data is ready to be pulled)
        while (retries>0):
            step = self.get_report_data().step
            if step == Job.JOB_STEP_COPYING:
                break
            l.debug("Report poll sleeping %i seconds (%i retries left)" % (self.report_poll_wait, retries))
            time.sleep(self.report_poll_wait)
            retries -= 1

        # remote passive job didn't enter 'COPYING' state
        if retries<=0:
            raise RuntimeError("Data from remote passive job not ready for copying after %i*%i seconds" % (self.report_poll_retries, self.report_poll_wait))

    # --------------------------------------------------------------------
    def outro(self):
        self.__notify_remote("done")
        Job.outro(self)


# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
