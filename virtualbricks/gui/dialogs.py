# -*- test-case-name: virtualbricks.tests.test_dialogs -*-
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

"""
Utility module to work with gtkbuilder.

When a new dialog is created a new glade project must be created. All the UI
definitions must live inside the `virtualbricks/gui/` package source
directory.

Then a new class should subclass the `Dialog` class and define at least the
`resource` class attribute with the name of the file (`data/resourcefile`). If
the `name` class attribute is not defined, the name of the new class should be
same of the main window in the ui definition.

Here the about dialog example.

    1. First of all the UI definition. The file is `about.ui` in the
       `virtualbricks/gui/data` directory. In this case the main widget/window
       is called "AboutDialog".

    2. Class definition. In `virtualbricks.gui.dialogs` the class `AboutDialog`
        is defined. The `resource` class attribute points to the UI definition
        and the `name` class attribute is not defined because the class name's
        match the main window's name.

    3. In the `__init__` all resources are initialized. It is much better to
        set here all the resource and not in setup.py because is easier to
        switch to another tools in the future. For example `pkgutil` in the
        standard library offer the `get_data()` function.

    4. Use the new code:

        dialogs.AboutDialog().run()

Note. Everytime a new dialog is created, a new gtk.Builder object is created,
this means that more than one dialogs of the same kind can live together. If
this is not desired is responsability of the programmer to do not (modal
dialogs, etc.). This means also that dialogs should be destroied. I'm not
really sure about this because when thare are no more references to the dialog
instance and the gc collect the object, the builder instance is collected too
and is the builder the only one that has an instance to the gtk.Dialog.

So, do not store a reference of the main widget or of the Dialog instance.

    # don't do this
    about = dialogs.AboutDialog()
    about.run()
    about.window # here the window is destroied
    # neither this
    awidget = dialogs.AboutDialog().get_object("awidget")


A note about Glade and the transition to gtk.Builder.

Glade supports gtk.builder but this must be specified in the project
paramentes. It is also possible to select the widget compatibility. The current
version of gtk in debian stable (squeeze) is 2.20, and 2.24 in debian testing
(wheeze) the, in a near future, new debian stable.

Exists a tools that help with the conversion, gtk-builder-convert, but its
results are not always excellent. A window at time conversion is highly
advised and possible with gtk-builder-convert.
"""

import os
import tempfile

import gtk
from twisted.internet import utils

from virtualbricks import version, tools, _compat, console
from virtualbricks.gui import graphics


log = _compat.getLogger(__name__)
NUMERIC = set(map(str, range(10)))
NUMPAD = set(map(lambda i: "KP_%d" % i, range(10)))
EXTRA = set(["BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab"])
VALIDKEY = NUMERIC | NUMPAD | EXTRA


if False:  # pyflakes
    _ = str


BUG_REPORT_ERRORS = {
    1: "Error in command line syntax.",
    2: "One of the files passed on the command line did not exist.",
    3: "A required tool could not be found.",
    4: "The action failed.",
    5: "No permission to read one of the files passed on the command line."
}

BODY = """-- DO NOT MODIFY THE FOLLOWING LINES --

 affects virtualbrick
"""


class Base(object):
    """Base class to work with gtkbuilder files.

    @ivar domain: Translation domain.
    @type domain: C{str} or C{None}

    @ivar resource: A gtkbuilder UI definition resource that a data finder can
            load.
    @type resource: C{str}

    @ivar name: The name of the main widget that must be load.
    @type name: C{str} or C{None}. If C{None} the name of the class is used.
    """

    domain = "virtualbricks"
    resource = None
    name = None

    def __init__(self):
        self.builder = builder = gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_file(graphics.get_filename("virtualbricks.gui",
                                                    self.resource))
        self.widget = builder.get_object(self.get_name())
        builder.connect_signals(self)

    def get_object(self, name):
        return self.builder.get_object(name)

    def get_name(self):
        if self.name:
            return self.name
        return self.__class__.__name__

    def show(self):
        self.widget.show()


class Window(Base):
    """Base class for all dialogs."""

    @property
    def window(self):
        return self.widget

    def show(self):
        self.widget.show()


class AboutDialog(Window):

    resource = "data/about.ui"

    def __init__(self):
        Window.__init__(self)
        self.window.set_version(version.short())
        # to handle show() instead of run()
        self.window.connect("response", lambda d, r: d.destroy())


class LoggingWindow(Window):

    resource = "data/logging.ui"

    def __init__(self, textbuffer):
        Window.__init__(self)
        self.textbuffer = textbuffer
        self.__bottom = True
        textview = self.get_object("textview1")
        textview.set_buffer(textbuffer)
        self.__insert_text_h = textbuffer.connect("changed",
                self.on_textbuffer_changed, textview)
        vadjustment = self.get_object("scrolledwindow1").get_vadjustment()
        self.__vadjustment_h = vadjustment.connect("value-changed",
                self.on_vadjustment_value_changed)
        self.scroll_to_end(textview, textbuffer)

    def scroll_to_end(self, textview, textbuffer):
        textview.scroll_to_mark(textbuffer.get_mark("end"), 0, True, 0, 1)

    def on_textbuffer_changed(self, textbuffer, textview):
        if self.__bottom:
            self.scroll_to_end(textview, textbuffer)

    def on_vadjustment_value_changed(self, adj):
        self.__bottom = adj.get_value() + adj.get_page_size() == \
                adj.get_upper()

    def on_LoggingWindow_destroy(self, window):
        self.textbuffer.disconnect(self.__insert_text_h)
        vadjustment = self.get_object("scrolledwindow1").get_vadjustment()
        vadjustment.disconnect(self.__vadjustment_h)

    def on_closebutton_clicked(self, button):
        self.window.destroy()

    def on_cleanbutton_clicked(self, button):
        self.textbuffer.set_text("")

    def on_savebutton_clicked(self, button):
        chooser = gtk.FileChooserDialog(title=_("Save as..."),
                action=gtk.FILE_CHOOSER_ACTION_SAVE,
                buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                        gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect("response", self.__on_dialog_response)
        chooser.show()

    def __on_dialog_response(self, dialog, response_id):
        try:
            if response_id == gtk.RESPONSE_OK:
                with open(dialog.get_filename(), "w") as fp:
                    self.save_to(fp)
        finally:
            dialog.destroy()

    def on_reportbugbutton_clicked(self, button):
        log.msg("Sending report bug")
        fd, filename = tempfile.mkstemp()
        os.write(fd, self.textbuffer.get_property("text"))
        gtk.link_button_set_uri_hook(None)
        exit_d = utils.getProcessOutputAndValue("xdg-email",
            ["--utf8", "--body", BODY, "--attach", filename,
             "new@bugs.launchpad.net"],
            dict(os.environ, MM_NOTTTY="1"))

        def success((out, err, code)):
            if code == 0:
                log.msg("Report bug sent succefully")
            elif code in BUG_REPORT_ERRORS:
                log.err(BUG_REPORT_ERRORS[code])
                log.err(err, show_to_user=False)
            else:
                log.err("Report bug failed with exit code %s" % code)
                log.err(err, show_to_user=False)

        exit_d.addCallbacks(success, log.err).addBoth(lambda _: os.close(fd))


class DisksLibraryDialog(Window):

    resource = "data/disklibrary.ui"
    cols_cell = (
        ("treeviewcolumn1", "cellrenderertext1", lambda i: i.name),
        ("treeviewcolumn2", "cellrenderertext2", lambda i: i.get_users()),
        ("treeviewcolumn3", "cellrenderertext3",
         lambda i: i.get_master_name()),
        ("treeviewcolumn4", "cellrenderertext4", lambda i: i.get_cows()),
        ("treeviewcolumn5", "cellrenderertext5", lambda i: i.get_size())
    )

    image = None

    def __init__(self, factory):
        Window.__init__(self)
        self.factory = factory
        model = self.get_object("liststore1")
        self.__add_handler_id = factory.connect("image-added",
                self.on_image_added, model)
        self.__del_handler_id = factory.connect("image-removed",
                self.on_image_removed, model)
        self.window.connect("destroy", self.on_window_destroy)
        self.tree_panel = self.get_object("treeview_panel")  # just handy
        self.config_panel = self.get_object("config_panel")  # just handy
        for column_name, cell_renderer_name, getter in self.cols_cell:
            column = self.get_object(column_name)
            cell_renderer = self.get_object(cell_renderer_name)
            column.set_cell_data_func(cell_renderer, self._set_cell_data,
                                      getter)
        for image in factory.disk_images:
            model.append((image,))

    def _set_cell_data(self, column, cell_renderer, model, iter, getter):
        image = model.get_value(iter, 0)
        cell_renderer.set_property("text", getter(image))
        color = "black" if image.exists() else "grey"
        cell_renderer.set_property("foreground", color)

    def show(self):
        Window.show(self)
        self.config_panel.hide()

    def on_window_destroy(self, widget):
        assert self.__add_handler_id is not None, \
                "Called on_window_destroy but no handler are associated"
        self.factory.disconnect(self.__add_handler_id)
        self.factory.disconnect(self.__del_handler_id)
        self.__add_handler_id = self.__del_handler_id = None

    def on_image_added(self, factory, image, model):
        model.append((image,))

    def on_image_removed(self, factory, image, model):
        iter = model.get_iter_first()
        while iter:
            if model.get_value(iter, 0) == image:
                model.remove(iter)
                break
        else:
            log.warning("image-removed signal is emitted but seems I don't"
                        " have that image")

    def on_close_button_clicked(self, button):
        self.window.destroy()

    def on_treeview_diskimages_row_activated(self, treeview, path, column):
        self.image = treeview.get_model()[path][0]
        self.tree_panel.hide()
        self.config_panel.show()

    def on_revert_button_clicked(self, button):
        self.config_panel.hide()
        self.tree_panel.show()

    def on_remove_button_clicked(self, button):
        assert self.image is not None, \
                "Called on_remove_button_clicked but self.image is not set."
        try:
            self.factory.remove_disk_image(self.image)
        except Exception:
            log.exception("Cannot remove image %s", self.image)
        self.tree_panel.show()
        self.config_panel.hide()

    def on_save_button_clicked(self, button):
        assert self.image is not None, \
                "Called on_save_button_clicked but no image is selected"
        name = self.get_object("name_entry").get_text()
        if self.image.name != name:
            self.image.rename(name)
        host = self.get_object("host_entry").get_text()
        if host != self.image.host:
            self.image.host = host
        ro = self.get_object("readonly_checkbutton").get_active()
        self.image.set_readonly(ro)
        desc = self.get_object("description_entry").get_text()
        self.image.set_description(desc)
        self.image = None
        self.tree_panel.show()
        self.config_panel.hide()

    def on_diskimages_config_panel_show(self, panel):
        assert self.image is not None, \
                "Called on_diskimages_config_panel_show but image is None"
        i, w = self.image, self.get_object
        w("name_entry").set_text(i.name)
        w("path_entry").set_text(i.path)
        w("description_entry").set_text(i.get_description())
        w("readonly_checkbutton").set_active(i.is_readonly())
        w("host_entry").set_text(i.host or "")


class UsbDevWindow(Window):

    resource = "data/usbdev.ui"

    def __init__(self, gui, output, vm):
        Window.__init__(self)
        self.gui = gui
        self.vm = vm
        log.msg("lsusb output:\n%s" % output)
        model = self.get_object("liststore1")
        self._populate_model(model, output)

    def _populate_model(self, model, output):
        for line in output.split("\n"):
            info = line.split(" ID ")[1]
            if " " in info:
                code, descr = info.split(" ", 1)
                model.append([code, descr])
        treeview = self.get_object("treeview1")
        selection = treeview.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)
        currents = self.vm.cfg.usbdevlist.split()
        # if currents:
        iter = model.get_iter_first()
        while iter:
            for dev in currents:
                ndev = model.get_value(iter, 0)
                if ndev == dev:
                    selection.select_iter(iter)
                    log.debug("found %s", dev)
                    break
            iter = model.iter_next(iter)

    def on_ok_button_clicked(self, button):
        treeview = self.get_object("treeview1")
        selection = treeview.get_selection()
        if selection:
            model, paths = selection.get_selected_rows()
            devs = " ".join(model[p[0]][0] for p in paths)

            if devs and not os.access("/dev/bus/usb", os.W_OK):
                log.error(_("Cannot access /dev/bus/usb. "
                            "Check user privileges."))
                self.gui.gladefile.get_widget("cfg_Qemu_usbmode_check"
                                             ).set_active(False)

            old = self.vm.cfg.usbdevlist
            self.vm.cfg.set('usbdevlist=' + devs)
            self.vm.update_usbdevlist(devs, old)
        self.window.destroy()


class ChangePasswordDialog(Window):

    resource = "data/changepwd.ui"

    def __init__(self, remote_host):
        Window.__init__(self)
        self.remote_host = remote_host
        self.get_object("password_entry").set_text(remote_host.password)

    def on_ChangePasswordDialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            password = self.get_object("password_entry").get_text()
            self.remote_host.password = password
        dialog.destroy()

    def on_password_entry_activate(self, entry):
        self.window.response(gtk.RESPONSE_OK)


class EthernetDialog(Window):

    resource = "data/ethernetdialog.ui"

    def __init__(self, gui, brick, plug=None):
        Window.__init__(self)
        self.gui = gui
        self.brick = brick
        self.plug = plug
        socks = self.get_object("sock_model")
        socks.append(("Host-only ad hoc network", "_hostonly"))
        if gui.config.femaleplugs:
            socks.append(("Vde socket", "_sock"))
        # TODO: can this operation made only once?
        for sock in gui.brickfactory.socks:
            if (sock.brick.get_type().startswith('Switch') or
                    gui.config.femaleplugs):
                socks.append((sock.nickname, sock.nickname))

        if plug:
            self.get_object("title_label").set_label(
                "<b>Edit ethernet interface</b>")
            self.get_object("ok_button").set_property("label", gtk.STOCK_EDIT)
            self.get_object("mac_entry").set_text(plug.mac)
            model = self.get_object("netmodel_model")
            i = model.get_iter_first()
            while i:
                if model.get_value(i, 0) == plug.model:
                    self.get_object("model_combo").set_active_iter(i)
                    break
                i = model.iter_next(i)

            i = socks.get_iter_first()
            while i:
                v = socks.get_value(i, 1)
                if ((plug.mode == "sock" and v == "_sock") or
                        (plug.mode == "hostonly" and v == "_hostonly") or
                        (plug.sock and plug.sock.nickname == v)):
                    self.get_object("sock_combo").set_active_iter(i)
                    break
                i = socks.iter_next(i)
        else:
            self.get_object("sock_combo").set_active(0)

    def is_valid(self, mac):
        return tools.mac_is_valid(mac)

    def add_plug(self, vlan=None):
        combo = self.get_object("sock_combo")
        sockname = combo.get_model().get_value(combo.get_active_iter(), 1)
        if sockname == "_sock":
            plug = self.brick.add_sock()
        elif sockname == "_hostonly":
            plug = self.brick.add_plug(sockname)
        else:
            plug = self.brick.add_plug()
            for sock in self.gui.brickfactory.socks:
                if sock.nickname == sockname:
                    plug.connect(sock)
                    break
        combo = self.get_object("model_combo")
        plug.model = combo.get_model().get_value(combo.get_active_iter(), 0)
        mac = self.get_object("mac_entry").get_text()
        if not self.is_valid(mac):
            log.error("MAC address %s is not valid, generating a random one",
                      mac)
            mac = tools.random_mac()
        plug.mac = mac
        if vlan is not None:
            plug.vlan = vlan

        self.gui.vmplugs.append((plug, ))

    def on_randomize_button_clicked(self, button):
        self.get_object("mac_entry").set_text(tools.random_mac())

    def on_EthernetDialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            vlan = None
            plug = self.plug
            if plug:
                vlan = plug.vlan
                if plug.mode == "sock":
                    self.brick.socks.remove(plug)
                else:
                    self.brick.plugs.remove(plug)

                get_value = self.gui.vmplugs.get_value
                iter_next = self.gui.vmplugs.iter_next
                i = self.gui.vmplugs.get_iter_first()
                while i:
                    l = get_value(i, 0)
                    if plug is l:
                        self.gui.vmplugs.remove(i)
                        break
                    i = iter_next(i)

            self.add_plug(vlan)
        dialog.destroy()


class ConfirmDialog(Window):

    resource = "data/confirmdialog.ui"

    def __init__(self, question, on_yes=None, on_yes_arg=None, on_no=None,
                 on_no_arg=None, ):
        Window.__init__(self)
        self.window.set_markup(question)
        self.on_yes = on_yes
        self.on_yes_arg = on_yes_arg
        self.on_no = on_no
        self.on_no_arg = on_no_arg

    def format_secondary_text(self, text):
        self.window.format_secondary_text(text)

    def on_ConfirmDialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_YES and self.on_yes:
            self.on_yes(self.on_yes_arg)
        elif response_id == gtk.RESPONSE_NO and self.on_no:
            self.on_no(self.on_no_arg)
        dialog.destroy()


class RenameDialog(Window):

    resource = "data/renamedialog.ui"
    name = "RenameDialog"

    def __init__(self, brick, factory):
        Window.__init__(self)
        self.brick = brick
        self.factory = factory
        self.get_object("entry").set_text(brick.name)


class RenameEventDialog(RenameDialog):

    def on_RenameDialog_response(self, dialog, response_id):
        try:
            if response_id == gtk.RESPONSE_OK:
                if self.brick.scheduled:
                    log.err(_("Cannot rename event: it is in use."))
                else:
                    new = self.get_object("entry").get_text()
                    self.factory.rename_event(self.brick, new)
        finally:
            dialog.destroy()


class RenameBrickDialog(RenameDialog):

    def on_RenameDialog_response(self, dialog, response_id):
        try:
            return
            if response_id == gtk.RESPONSE_OK:
                if self.event.scheduled:
                    log.err(_("Cannot rename event: it is in use."))
                else:
                    new = self.get_object("entry").get_text()
                    self.factory.rename_event(self.event, new)
        finally:
            dialog.destroy()


class NewEventDialog(Window):

    resource = "data/newevent.ui"

    def __init__(self, gui):
        Window.__init__(self)
        self.gui = gui

    def on_delay_entry_key_press_event(self, entry, event):
        if gtk.gdk.keyval_name(event.keyval) not in VALIDKEY:
            return True
        elif gtk.gdk.keyval_name(event.keyval) == "Return":
            self.window.response(gtk.RESPONSE_OK)
            return True

    def on_name_entry_key_press_event(self, entry, event):
        if gtk.gdk.keyval_name(event.keyval) == "Return":
            self.window.response(gtk.RESPONSE_OK)
            return True

    def get_event_type(self):
        for name in "start", "stop", "config", "shell", "collation":
            button = self.get_object(name + "_button")
            if button.get_active():
                return name
        return "shell"  # this condition show not be reached

    def on_NewEventDialog_response(self, dialog, response_id):
        try:
            if response_id == gtk.RESPONSE_OK:
                name = self.get_object("name_entry").get_text()
                delay = self.get_object("delay_entry").get_text()
                type = self.get_event_type()
                event = self.gui.brickfactory.new_event(name)
                event.set({"delay": int(delay)})
                if type in ("start", "stop", "collation"):
                    action = "off" if type == "stop" else "on"
                    bricks = self.gui.brickfactory.bricksmodel
                    dialog_n = BrickSelectionDialog(event, action, bricks)
                elif type == "shell":
                    action = console.VbShellCommand("new switch myswitch")
                    event.set({"actions": [action]})
                    dialog_n = ShellCommandDialog(event)
                else:
                    raise RuntimeError("Invalid event type %s" % type)
                dialog_n.window.set_transient_for(self.gui.widg["main_win"])
                dialog_n.show()
        finally:
            dialog.destroy()


class BrickSelectionDialog(Window):

    resource = "data/brickselection.ui"

    def __init__(self, event, action, bricks):
        Window.__init__(self)
        self.event = event
        self.action = action
        self.added = set()

        self.availables_f = bricks.filter_new()
        self.availables_f.set_visible_func(self.is_not_added, self.added)
        availables_treeview = self.get_object("availables_treeview")
        availables_treeview.set_model(self.availables_f)
        self.added_f = bricks.filter_new()
        self.added_f.set_visible_func(self.is_added, self.added)
        added_treeview = self.get_object("added_treeview")
        added_treeview.set_model(self.added_f)

        avail_c = self.get_object("availables_treeviewcolumn")
        icon_cr1 = self.get_object("icon_cellrenderer1")
        avail_c.set_cell_data_func(icon_cr1, self.set_icon)
        name_cr1 = self.get_object("name_cellrenderer1")
        avail_c.set_cell_data_func(name_cr1, self.set_name)
        added_c = self.get_object("added_treeviewcolumn")
        icon_cr2 = self.get_object("icon_cellrenderer2")
        added_c.set_cell_data_func(icon_cr2, self.set_icon)
        name_cr2 = self.get_object("name_cellrenderer2")
        added_c.set_cell_data_func(name_cr2, self.set_name)

    def is_not_added(self, model, iter, added):
        brick = model.get_value(iter, 0)
        return brick not in added

    def is_added(self, model, iter, added):
        brick = model.get_value(iter, 0)
        return brick in added

    def set_icon(self, column, cell_renderer, model, iter):
        brick = model.get_value(iter, 0)
        pixbuf = graphics.pixbuf_for_running_brick_at_size(brick, 48, 48)
        cell_renderer.set_property("pixbuf", pixbuf)

    def set_name(self, column, cell_renderer, model, iter):
        brick = model.get_value(iter, 0)
        cell_renderer.set_property("text", "{0} ({1})".format(
            brick.name, brick.get_type()))

    def _move_to(self, treeview, action):
        model, iter = treeview.get_selection().get_selected()
        if iter:
            action(model[iter][0])
            self.added_f.refilter()
            self.availables_f.refilter()

    def on_add_button_clicked(self, button):
        self._move_to(self.get_object("availables_treeview"), self.added.add)

    def on_remove_button_clicked(self, button):
        self._move_to(self.get_object("added_treeview"), self.added.remove)

    def on_availables_treeview_row_activated(self, treeview, path, column):
        self._move_to(treeview, self.added.add)

    def on_added_treeview_row_activated(self, treeview, path, column):
        self._move_to(treeview, self.added.remove)

    def on_BrickSelectionDialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            actions = [console.VbShellCommand("%s %s" % (b.name, self.action))
                       for b in self.added]
            self.event.set({"actions": actions})
            log.msg("Event created successfully")
        dialog.destroy()


class EventControllerMixin(object):

    resource = "data/eventconfig.ui"

    def setup_controller(self, event):
        self.get_object("action_treeview").get_selection().set_mode(
            gtk.SELECTION_MULTIPLE)
        self.get_object("sh_cellrenderer").set_activatable(True)
        self.get_object("action_cellrenderer").set_property("editable", True)
        model = self.get_object("actions_liststore")
        for action in event.cfg["actions"]:
            model.append((action, isinstance(action, console.ShellCommand)))
        model.append(("", False))

    def on_action_cellrenderer_edited(self, cell_renderer, path, new_text):
        model = self.get_object("actions_liststore")
        iter = model.get_iter(path)
        if new_text:
            model.set_value(iter, 0, new_text)
            if model.iter_next(iter) is None:
                model.append(("", False))
        elif model.iter_next(iter) is not None:
            model.remove(iter)
        else:
            model.set_value(iter, 0, new_text)

    def on_sh_cellrenderer_toggled(self, cell_renderer, path):
        model = self.get_object("actions_liststore")
        iter = model.get_iter(path)
        model.set_value(iter, 1, not cell_renderer.get_active())

    def configure_event(self, event, attrs):
        model = self.get_object("actions_liststore")
        f = (console.VbShellCommand, console.ShellCommand)
        attrs["actions"] = [f[row[1]](row[0]) for row in model if row[0]]
        event.set(attrs)


class ShellCommandDialog(Window, EventControllerMixin):

    resource = "data/eventcommand.ui"

    def __init__(self, event):
        Window.__init__(self)
        self.event = event
        self.setup_controller(event)

    def on_ShellCommandDialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            self.configure_event(self.event, {})
        dialog.destroy()
