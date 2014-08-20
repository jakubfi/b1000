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
import logging as l
import MySQLdb
import ConfigParser

# ------------------------------------------------------------------------
class Values:
    pass

# ------------------------------------------------------------------------
class ReportFile:

    params_required = ['type', 'path']
    params_allowed = []

    # --------------------------------------------------------------------
    def __init__(self, job, cfg, name):

        self.job = job
        self.cfg = cfg
        self.name = name
        self.sname = "report:" + self.name

        self.cfg.validate(self.sname, self.params_required, self.params_allowed)
        l.debug("Adding file report '%s' to job '%s'" % (name, job.real_name))

        self.path = cfg.get(self.sname, "path")

        # set report dir in job for 'passive' destination to work properly
        if not self.job.report_dir:
            self.job.report_dir = self.path
        else:
            raise SyntaxError("Job may have only one 'file' report destination")


    # --------------------------------------------------------------------
    def update(self):

        rd = self.job.get_report_data()

        start_time = time.strftime("%Y-%m-%d %H:%M:%S", rd.start_time)
        safe_start_time = time.strftime("%Y-%m-%d-%H-%M-%S", rd.start_time)

        report = ConfigParser.RawConfigParser()
        jname = 'jobstatus:' + rd.name
        report.add_section(jname)

        for d in rd.destinations:
            dname = 'dest:' + d.name
            report.add_section(dname)

        report.set(jname, 'host', rd.host)
        report.set(jname, 'name', rd.name)
        report.set(jname, 'instance', rd.instance)
        report.set(jname, 'master_host', rd.master_host)
        report.set(jname, 'master_instance', rd.master_instance)
        report.set(jname, 'direction', rd.jdirection)
        report.set(jname, 'start_time', start_time)
        report.set(jname, 'step', rd.step)
        report.set(jname, 'status', rd.status)
        report.set(jname, 'data_age', rd.data_age)

        # write all destinations
        for d in rd.destinations:
            dname = 'dest:' + d.name
            report.set(dname, 'type', d.dtype)
            report.set(dname, 'path', d.path)
            report.set(dname, 'status', d.status)

        reportname = self.path + "/" + rd.name + "-" + rd.instance + "-" + safe_start_time + ".b1k"
        r = open(reportname, 'wb')
        report.write(r)
        r.close()

# ------------------------------------------------------------------------
class ReportMysql:

    params_required = ['type', 'server', 'db', 'user', 'password']
    params_allowed = []

    # --------------------------------------------------------------------
    def __init__(self, job, cfg, name):

        self.job = job
        self.cfg = cfg
        self.name = name
        self.sname = "report:" + self.name

        self.cfg.validate(self.sname, self.params_required, self.params_allowed)

        rd = self.job.get_report_data()

        l.debug("Adding MySQL report '%s' to job '%s'" % (name, rd.name))

        self.server = cfg.get(self.sname, "server")
        self.db = cfg.get(self.sname, "db")
        self.user = cfg.get(self.sname, "user")
        self.password = cfg.get(self.sname, "password")
        self.__check_connection()

    # --------------------------------------------------------------------
    def __check_connection(self):
        db = MySQLdb.connect(host=self.server, user=self.user, passwd=self.password, db=self.db)
        c = db.cursor()
        rows = c.execute("SELECT count(*) from jobs")
        result = c.fetchone()
        c.close()
        db.close()

    # --------------------------------------------------------------------
    def update(self):

        rd = self.job.get_report_data()

        start_time = time.strftime("%Y-%m-%d %H:%M:%S", rd.start_time)

        db = MySQLdb.connect(host=self.server, user=self.user, passwd=self.password, db=self.db)
        c = db.cursor()

        # write job
        rows = c.execute("""
        INSERT INTO jobs (host, name, instance, master_host, master_instance, direction, start_time, step, status, data_age)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE step = %s, status = %s
        """, (rd.host, rd.name, rd.instance, rd.master_host, rd.master_instance, rd.jdirection, start_time, rd.step, rd.status, rd.data_age, rd.step, rd.status))

        job_id = c.lastrowid

        # nothing inserted, nothing updated, let's find the job id
        if rows == 0 and job_id == 0:
            c.execute("""
            SELECT job_id from jobs where start_time = %s and host = %s and name = %s and instance = %s
            """, (start_time, rd.host, rd.name, rd.instance))
            (job_id,) = c.fetchone()

        # write all destinations
        for d in rd.destinations:
            rows = c.execute("""
            INSERT INTO copies (job_id, destination, type, path, status)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status = %s
            """, (job_id, d.name, d.dtype, d.path, d.status, d.status))

        c.close()
        db.commit()
        db.close()


# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
