# -*- test-case-name: virtualbricks.tests.test_configfile -*-
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
import os.path
import errno
import re
import shutil
import traceback
import contextlib

from twisted.python import failure

from virtualbricks import _compat, settings, virtualmachines


if False:  # pyflakes
    _ = str


log = _compat.getLogger(__name__)


@contextlib.contextmanager
def backup(original, filename):
    created = False
    # create a new backup file of the project
    if os.path.isfile(original):
        shutil.copyfile(original, filename)
        created = True
    yield
    if created:
        # remove the project backup file
        os.remove(filename)


def restore_backup(filename, fbackup):
    # check if there's a project backup to restore and if its size is
    # different from current project file
    filename_back = filename + ".back"
    if os.path.isfile(fbackup):
        log.info("I found a backup project file, I'm going to restore it!")
        try:
            os.rename(filename, filename_back)
            log.info("Saved project to %s.", filename_back)
        except OSError, e:
            if e.errno == errno.EXDEV:
                try:
                    shutil.copyfile(filename, filename_back)
                except IOError:
                    log.warning("Cannot save to backup file %s.\n%s",
                                filename_back, traceback.format_exc())
                    log.error("Cannot create a backup of the broject.")
            elif e.errno == errno.ENOENT:
                pass
            else:
                log.warning("Cannot save to backup file %s.\n%s",
                            filename_back, traceback.format_exc())
                log.error("Cannot create a backup of the broject.")
        # restore backup file
        log.info("I found a backup project file, I'm going to restore it!")

        try:
            os.rename(fbackup, filename)
            log.info("Saved project to %s.", filename_back)
            log.error(_("A backup file for the current project has been "
                        "restored.\nYou can find more informations looking in "
                        "View->Messages."))
        except OSError, e:
            if e.errno == errno.EXDEV:
                try:
                    shutil.copyfile(fbackup, filename)
                    os.remove(fbackup)
                except IOError:
                    log.warning("Cannot restore backup file %s.\n%s",
                                fbackup, traceback.format_exc())
                    log.error("Cannot restore backup of the broject.")
                finally:
                    try:
                        os.remove(fbackup)
                    except OSError:
                        pass
            elif e.errno == errno.ENOENT:
                pass
            else:
                log.warning("Cannot restore backup file %s.\n%s",
                            fbackup, traceback.format_exc())
                log.error("Cannot restore backup of the broject.")


class ConfigFile:

    def save(self, factory, obj_or_str):
        """Save the current project.

        @param obj_or_str: The filename of file object where to save the
                           project.
        @type obj_or_str: C{str} or an object that implements the file
                          interface.
        """

        if isinstance(obj_or_str, basestring):
            filename = obj_or_str
            log.debug("CONFIG DUMP on " + filename)
            fp = None
            with backup(filename, filename + "~"):
                head, tail = os.path.split(filename)
                tmpfile = os.path.join(head, "." + tail + ".sav")
                with open(tmpfile, "w") as fp:
                    self.save_to(factory, fp)
                os.rename(tmpfile, filename)
        else:
            self.save_to(factory, obj_or_str)

    def save_to(self, factory, fileobj):
        # with factory.lock():
            return self.__save_to(factory, fileobj)

    def __save_to(self, factory, fileobj):
        # Remote hosts
        for r in factory.remote_hosts:
            fileobj.write('[RemoteHost:' + r.addr[0] + ']\n')
            fileobj.write('port=' + str(r.addr[1]) + '\n')
            fileobj.write('password=' + r.password + '\n')
            fileobj.write('baseimages=' + r.baseimages + '\n')
            fileobj.write('qemupath=' + r.qemupath + '\n')
            fileobj.write('vdepath=' + r.vdepath + '\n')
            fileobj.write('bricksdirectory=' + r.bricksdirectory + '\n')
            if r.autoconnect:
                fileobj.write('autoconnect=True\n\n')
            else:
                fileobj.write('autoconnect=False\n\n')

        # Disk Images
        for img in factory.disk_images:
            fileobj.write('[DiskImage:' + img.name + ']\n')
            fileobj.write('path=' + img.path + '\n')
            fileobj.write("\n")

        for event in factory.events:
            event.save_to(fileobj)

        socks = []
        plugs = []
        for brick in iter(factory.bricks):
            brick.save_to(fileobj)
            if brick.get_type() == "Qemu":
                socks.extend(brick.socks)
            plugs.extend(p for p in brick.plugs if p.sock is not None)

        for sock in socks:
            t = "sock|{s.brick.name}|{s.nickname}|{s.model}|{s.mac}\n"
            fileobj.write(t.format(s=sock))

        for plug in plugs:
            if plug.brick.get_type() == 'Qemu':
                if plug.mode == 'vde':
                    t = ("link|{p.brick.name}|{p.sock.nickname}|{p.model}|"
                         "{p.mac}\n")
                else:
                    t = "userlink|{p.brick.name}||{p.model}|{pl.mac}\n"
                fileobj.write(t.format(p=plug))
            elif plug.sock is not None:
                t = "link|{p.brick.name}|{p.sock.nickname}\n"
                fileobj.write(t.format(p=plug))

    def restore(self, factory, str_or_obj):
        if isinstance(str_or_obj, basestring):
            filename = str_or_obj
            restore_backup(filename, filename + "~")
            log.info("Open %s project", filename)
            with open(filename) as fp:
                self.restore_from(factory, fp)
        else:
            self.restore_from(factory, str_or_obj)

    def restore_from(self, factory, fileobj):
        # with factory.lock():
            return self.__restore_from(factory, fileobj)

    def __restore_from(self, factory, fileobj):
        l = fileobj.readline()
        b = None
        while (l):
            l = re.sub(' ', '', l)
            if re.search("\A.*sock\|", l) and len(l.split("|")) >= 3:
                l = l.rstrip('\n')
                log.debug("sock detected")
                for bb in iter(factory.bricks):
                    if bb.name == l.split("|")[1]:
                        if (bb.get_type() == 'Qemu'):
                            sockname = l.split('|')[2]
                            model = l.split("|")[3]
                            macaddr = l.split("|")[4]
                            pl = bb.add_sock(macaddr, model)
                            idx = len(bb.plugs) + len(bb.socks)
                            log.debug("added eth%d" % idx)

            if re.search("\A.*link\|", l) and len(l.split("|")) >= 3:
                l = l.rstrip('\n')
                log.debug("link detected")
                for bb in iter(factory.bricks):
                    if bb.name == l.split("|")[1]:
                        if (bb.get_type() == 'Qemu'):
                            sockname = l.split('|')[2]
                            model = l.split("|")[3]
                            macaddr = l.split("|")[4]
                            this_sock = "?"
                            if sockname == '_hostonly':
                                this_sock = virtualmachines.hostonly_sock
                            else:
                                for s in factory.socks:
                                    if s.nickname == sockname:
                                        this_sock = s
                                        break
                            if this_sock == '?':
                                log.warning("socket '%s' not found while "
                                            "parsing following line: %s\n. "
                                            "Skipping.", sockname, l)
                                continue
                            pl = bb.add_plug(this_sock, macaddr, model)
                            idx = len(bb.plugs) + len(bb.socks)
                            log.debug("added eth%d" % idx)
                        else:
                            bb.config_socks.append(
                                l.split('|')[2].rstrip('\n'))

            if l.startswith('['):
                ntype = l.lstrip('[').split(':')[0]
                name = l.split(':')[1].rstrip(']\n')

                log.info("new %s : %s", ntype, name)
                try:
                    if ntype == 'Event':
                        factory.newevent(ntype, name)
                        component = factory.get_event_by_name(name)
                    elif ntype == 'DiskImage':
                        log.debug("Found Disk image %s" % name)
                        path = ""
                        host = None
                        readonly = False
                        l = fileobj.readline().rstrip("\n")
                        while l and not l.startswith('['):
                            l = l.strip()
                            if not l:
                                l = fileobj.readline()
                                continue
                            k, v = l.split("=", 1)
                            if k == 'path':
                                path = str(v)
                            l = fileobj.readline()
                        if factory.is_in_use(name):
                            log.info("Skipping disk image, name %s already in "
                                     "use", name)
                            continue
                        if host is None and not os.access(path, os.R_OK):
                            continue
                        img = factory.new_disk_image(path)
                        continue

                    elif ntype == 'RemoteHost':
                        log.debug("Found remote host %s" % name)
                        newr = factory.get_host_by_name(name)
                        l = fileobj.readline()
                        while l and not l.startswith('['):
                            k, v = l.rstrip("\n").split("=")
                            if k == 'password':
                                newr.password = str(v)
                            elif k == 'autoconnect' and v == 'True':
                                newr.autoconnect = True
                            elif k == 'baseimages':
                                newr.baseimage = str(v)
                            elif k == 'vdepath':
                                newr.vdepath = str(v)
                            elif k == 'qemupath':
                                newr.qemupath = str(v)
                            elif k == 'bricksdirectory':
                                newr.bricksdirectory = str(v)
                            l = fileobj.readline()
                        if newr.autoconnect:
                            newr.connect()
                        continue
                    else:  # elif ntype == 'Brick'
                        factory.newbrick(ntype, name)
                        component = factory.get_brick_by_name(name)

                except Exception as e:
                    log.err(failure.Failure(e), "Bad config line: %s" % l)
                    l = fileobj.readline()
                    continue

                component.load_from(fileobj)
                l = fileobj.readline()
                continue

            l = fileobj.readline()

        for b in iter(factory.bricks):
            for c in b.config_socks:
                factory.connect_to(b, c)


_config = ConfigFile()


def save(factory, filename=None):
    if filename is None:
        filename = settings.get("current_project")
    _config.save(factory, filename)


def safe_save(factory, filename=None):
    try:
        save(factory, filename)
    except Exception:
        log.exception("Error while saving configuration file")


def restore(factory, filename=None):
    if filename is None:
        filename = settings.get("current_project")
    factory.reset()
    _config.restore(factory, filename)


def restore_last_project(factory):
    """Restore the last project if found or create a new one."""

    try:
        os.mkdir(settings.VIRTUALBRICKS_HOME)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    try:
        os.mkdir(settings.get("baseimages"))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    try:
        restore(factory)
    except IOError as e:
        if e.errno == errno.ENOENT:
            if settings.get("current_project") != settings.DEFAULT_PROJECT:
                log.error("Cannot find last project '%s': file not found. "
                          "A new project will be created with that path.",
                          settings.get("current_project"))
        else:
            raise
