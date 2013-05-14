# -*- test-case-name: virtualbricks.tests.test_bricks -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import os
import sys
import time
import socket
import select
import re
import copy
import subprocess
import logging

from virtualbricks import base, errors
from virtualbricks.settings import MYPATH
from virtualbricks.brickconfig import BrickConfig
from virtualbricks.console import RemoteHost


log = logging.getLogger(__name__)


if False:  # pyflakes
    _ = str


class Brick(base.Base):

    active = False
    run_condition = False
    proc = None
    gui_changed = False
    need_restart_to_apply_changes = False
    internal_console = None
    terminal = "vdeterm"
    _name = None

    def get_name(self):
        return self._name

    getname = get_name

    def set_name(self, name):
        self._name = name

    name = property(get_name, set_name)

    def __init__(self, factory, name, homehost=None):
        base.Base.__init__(self)
        self.factory = factory
        self._name = name
        self.settings = self.factory.settings
        self.plugs = []
        self.socks = []
        self.cfg = BrickConfig()
        self.cfg.pon_vbevent = ""
        self.cfg.poff_vbevent = ""
        self.command_builder = dict()
        self.config_socks = []

        if (homehost):
            self.set_host(homehost)
        else:
            self.homehost = None

    # each brick must overwrite this method
    def prog(self):
        raise NotImplementedError("Brick.prog")

    def rewrite_sock_server(self, v):
        f = os.path.basename(v)
        return MYPATH + "/" + f

    def set_host(self, host):
        self.cfg.homehost = host
        self.homehost = None
        if len(host) > 0:
            for existing in self.factory.remote_hosts:
                if existing.addr[0] == host:
                    self.homehost = existing
                    break
            if not self.homehost:
                self.homehost = RemoteHost(self.factory, host)
                self.factory.remote_hosts.append(self.homehost)
            self.factory.remotehosts_changed = True

    def restore_self_plugs(self):  # DO NOT REMOVE
        pass

    def clear_self_socks(self, sock=None):  # DO NOT REMOVE
        pass

    def __deepcopy__(self, memo):
        newname = self.factory.normalize(self.factory.next_name(
            "Copy_of_%s" % self.name))
        new_brick = type(self)(self.factory, newname)
        new_brick.cfg = copy.deepcopy(self.cfg, memo)
        return new_brick

    def path(self):
        return "%s/%s.ctl" % (MYPATH, self.name)

    def console(self):
        return "%s/%s.mgmt" % (MYPATH, self.name)

    def cmdline(self):
        return ""

    def pidfile(self):
        return "/tmp/%s.pid" % self.name
    pidfile = property(pidfile)

    def on_config_changed(self):
        self.emit("changed")

    def configured(self):
        return False

    def properly_connected(self):
        for p in self.plugs:
            if not p.configured():
                return False
        return True

    def check_links(self):
        for p in self.plugs:
            if not p.connected():
                return False
        return True

    def initialize(self, attrlist):
        """TODO attrs : dict attr => value"""
        for attr in attrlist:
            k = attr.split("=")[0]
            self.cfg.set(attr)
            if k == 'homehost':
                self.set_host(attr.split('=')[1])
            if k == 'sock':
                s = self.rewrite_sock_server(attr.split('=')[1])
                self.cfg.sock = s

    def configure(self, attrlist):
        """TODO attrs : dict attr => value"""
        self.initialize(attrlist)
        # TODO brick should be gobject and a signal should be launched
        self.emit("changed")
        if self.homehost and self.homehost.connected:
            self.homehost.putconfig(self)

    def connect(self, endpoint):
        for p in self.plugs:
            if not p.configured():
                if p.connect(endpoint):
                    self.emit("changed")
                    self.gui_changed = True
                    return True
        return False

    def disconnect(self):
        for p in self.plugs:
            if p.configured():
                p.disconnect()
        self.emit("changed")

    ############################
    ########### Poweron/Poweroff
    ############################

    def poweron(self):
        if self.factory.TCP is None:
            if not self.configured():
                raise errors.BadConfigError("Brick %s not configured",
                                            self.name)
            if not self.properly_connected():
                raise errors.NotConnectedError("Brick %s not properly "
                                               "connected", self.name)
            if not self.check_links():
                raise errors.LinkLoopError("Link loop detected")
        self._poweron()
        self.emit("changed")

    def build_cmd_line(self):
        res = []

        for (switch, v) in self.command_builder.items():
            if not switch.startswith("#"):
                if callable(v):
                    value = v()
                else:
                    value = self.cfg.get(v)
                if value is "*":
                    res.append(switch)
                elif value is not None and len(value) > 0:
                    if not switch.startswith("*"):
                        res.append(switch)
                    res.append(value)
        return res

    def args(self):
        res = []
        res.append(self.prog())
        for c in self.build_cmd_line():
            res.append(c)
        return res

    def escape(self, arg):
        arg = re.sub('"', '\\"', arg)
        #arg = '"' + arg + '"'
        return arg

    def _poweron(self):
        if self.proc is not None:
            return
        try:
            command_line = self.args()
        except Exception:
            log.exception("Error while retrieving the list of arguments.")
            return

        if self.needsudo():
            sudoarg = ""
            if self.get_type() == 'Qemu':
                command_line = []
                command_line.append(self.settings.get("sudo"))
                for cmdarg in self.args():
                    command_line.append(self.escape(cmdarg))
                command_line.append('-pidfile')
                command_line.append(self.pidfile)

            else:
                for cmdarg in command_line:
                    sudoarg += cmdarg + " "
                sudoarg += "-P %s" % self.pidfile
                command_line[0] = self.settings.get("sudo")
                command_line[1] = self.escape(sudoarg)
        log.debug(_("Starting: '%s'"), ' '.join(command_line))
        if self.homehost:
            if not self.homehost.connected:
                log.error(_("Error: You must be connected to the "
                            "host to perform this action"))
                return
            else:
                # Initiate RemoteHost startup:
                self.homehost.send(self.name + " on")
                return
        else:
            # LOCAL BRICK
            try:
                # out and err files (if configured) for saving VM output
                out = subprocess.PIPE
                if self.get_type() == 'Qemu':
                    if self.cfg.stdout != "":
                        out = open(self.cfg.stdout, "wb")
                self.proc = subprocess.Popen(command_line,
                                             stdin=subprocess.PIPE, stdout=out,
                                             stderr=subprocess.STDOUT)
            except OSError:
                log.error(_("OSError: Brick startup failed. Check your "
                            "configuration!"))
                return

            if self.proc:
                self.pid = self.proc.pid
            else:
                if self.proc is not None:
                    log.error(_("Brick startup failed. Check your"
                              " configuration!\nMessage:\n%s"),
                            "\n".join(self.proc.stdout.readlines()))
                else:
                    log.error(_("Brick startup failed. Check your"
                                "configuration!\n"))
                return

            if (self.open_internal_console and
                    callable(self.open_internal_console)):
                self.internal_console = self.open_internal_console()

        self.factory.emit("brick-started", self.name)
        self.run_condition = True
        self.post_poweron()

    def poweroff(self):
        if self.proc is None:
            return
        if self.run_condition is False:
            return
        self.run_condition = False
        if self.homehost:
            self.proc = None
            self.homehost.send(self.name + " off\n")
            return

        log.debug(_("Shutting down %s"), self.name)
        is_running = self.proc.poll() is None
        if is_running:
            if self.needsudo():
                with open(self.pidfile) as pidfile:
                    pid = pidfile.readline().rstrip("\n")
                    ret = os.system(self.settings.get('sudo') + ' "kill ' +
                                    pid + '"')
            else:
                if self.proc.pid <= 1:
                    return

                pid = self.proc.pid
                try:
                    self.proc.terminate()
                except Exception, e:
                    log.error(_("can not send SIGTERM: '%s'"), e)
                ret = os.system('kill ' + str(pid))
            if ret != 0:
                log.error(_("can not stop brick error code: %s"), ret)
                return

        ret = None
        while ret is None:
            ret = self.proc.poll()
            time.sleep(0.2)

        self.proc = None
        self.need_restart_to_apply_changes = False
        if (self.close_internal_console and
            callable(self.close_internal_console)):
            self.close_internal_console()
        self.internal_console = None
        self.factory.emit("brick-stopped", self.name)
        self.post_poweroff()

    def post_poweron(self):
        self.active = True
        self.start_related_events(on=True)

    def post_poweroff(self):
        self.active = False
        self.start_related_events(off=True)

    def start_related_events(self, on=True, off=False):

        if on is False and off is False:
            return

        if ((off and not self.cfg.poff_vbevent) or
            (on and not self.cfg.pon_vbevent)):
            return

        if off:
            ev = self.factory.get_event_by_name(self.cfg.poff_vbevent)
        elif on:
            ev = self.factory.get_event_by_name(self.cfg.pon_vbevent)

        if ev:
            ev.poweron()
        else:
            log.warning("Warning. The Event '%s' attached to Brick '%s' is "
                        "not available. Skipping execution.",
                        self.cfg.poff_vbevent, self.name)

    #############################
    # Console related operations.
    #############################
    def has_console(self, closing=False):
        for i in range(1, 10):
            if (self.proc is not None and self.console() and
                os.path.exists(self.console())):
                return True
            else:
                if closing:
                    return False
                time.sleep(0.5)
        return False

    def open_console(self):
        log.debug("open_console")
        if not self.has_console():
            return

        if os.access(self.settings.get('term'), os.X_OK):
            cmdline = [self.settings.get('term'), '-T', self.name, '-e',
                       self.terminal, self.console()]
        elif os.access(self.settings.get('alt-term'), os.X_OK):
            cmdline = [self.settings.get('alt-term'), '-t', self.name, '-e',
                       self.terminal + " " + self.console()]
        else:
            log.error(_("Error: cannot start a terminal emulator"))
            return
        try:
            # console = subprocess.Popen(cmdline)
            subprocess.Popen(cmdline)
        except:
            log.exception(_("Error running command line %s"), cmdline)
            return

    # Must be overridden in Qemu to use appropriate console as internal
    # (stdin, stdout?)
    def open_internal_console(self):
        log.debug("open_internal_console")
        if not self.has_console():
            log.debug(_("%s does not have a console"), self.get_type())
            return None
        for i in range(1, 10):
            try:
                time.sleep(0.5)
                c = socket.socket(socket.AF_UNIX)
                c.connect(self.console())
            except:
                pass
            else:
                return c
        log.error(_("%s: error opening internal console"), self.get_type())
        return None

    def send(self, msg):
        if self.internal_console is None or not self.active:
            log.debug("%s: cancel send", self.get_type())
            return
        try:
            log.debug("%s: sending '%s'", self.get_type(), msg)
            self.internal_console.send(msg)
        except Exception:
            log.exception("%s: send failed", self.get_type())

    def recv(self):
        log.debug("recv")
        if self.internal_console is None:
            return ''
        res = ''
        p = select.poll()
        p.register(self.internal_console, select.POLLIN)
        while True:
            pollret = p.poll(300)
            if (len(pollret) == 1 and pollret[0][1] == select.POLLIN):
                line = self.internal_console.recv(100)
                res += line
            else:
                break
        return res

    def close_internal_console(self):
        if not self.has_console(closing=True):
            return
        self.internal_console.close()

    def close_tty(self):
        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()

    def get_parameters(self):
        raise NotImplementedError('Bricks.get_parameters() not implemented')

    def get_state(self):
        """return state of the brick"""
        if self.proc is not None:
            state = _('running')
        elif not self.properly_connected():
            state = _('disconnected')
        else:
            state = _('off')
        return state
