#!/usr/bin/python
#
# GUI Module for standalone subscription-manager cli 
#
# Copyright (c) 2010 Red Hat, Inc.
#
# Authors: Pradeep Kilambi <pkilambi@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

import os
import sys
import shutil
sys.path.append('/usr/share/rhsm')

import gtk
import gtk.glade
import gobject
import signal

import messageWindow
import hwprobe
import managerlib
import connection

from certlib import EntitlementDirectory, ProductDirectory, ConsumerIdentity
import gettext
_ = gettext.gettext
gettext.textdomain("subscription-manager")
gtk.glade.bindtextdomain("subscription-manager")

gladexml = "/usr/share/rhsm/gui/data/standaloneH.glade"
UEP = connection.UEPConnection()
ENT_CONFIG_DIR="/etc/pki/entitlement/product/"

class ManageSubscriptionPage:
    """
     Main subscription Manager Window
    """
    def __init__(self):
        self.subsxml = gtk.glade.XML(gladexml, "dialog_updates", domain="subscription-manager")
        self.vbox = \
                        self.subsxml.get_widget("dialog-vbox1")
        self.populateProductDialog()
        self.updateMessage()
        dic = { "on_button_close_clicked" : gtk.main_quit,
                "account_settings_clicked_cb" : self.loadAccountSettings,
                "on_button_add1_clicked" : self.addSubButtonAction,
                "on_button_update1_clicked" : self.updateSubButtonAction,
                "on_button_unsubscribe1_clicked" : self.onUnsubscribeAction,
            }
        self.subsxml.signal_autoconnect(dic)
        self.mainWin = self.subsxml.get_widget("dialog_updates")
        self.mainWin.connect("delete-event", gtk.main_quit)
        self.mainWin.connect("hide", gtk.main_quit)

        self.mainWin.show_all()

    def loadAccountSettings(self, button):
        login_page = LoginPage()
        login_page.loginPagePrepare()
        return True

    def reviewSubscriptionPagePrepare(self):
        entdir = EntitlementDirectory()
        self.vbox.show_all()

    def addSubButtonAction(self, button):
        AddSubscriptionScreen()

    def updateSubButtonAction(self, button):
        UpdateSubscriptionScreen()

    def populateProductDialog(self):
        self.productList = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING)
        self.warn_count = 0
        for product in managerlib.getInstalledProductStatus():
            self.productList.append(product)
            if product[1] in ["Expired", "Not Subscribed"]:
                self.warn_count += 1
        self.tv_products =  self.subsxml.get_widget("treeview_updates")
        self.tv_products.set_model(self.productList)

        self.tv_products.set_rules_hint(True)

        col = gtk.TreeViewColumn(_("Product"), gtk.CellRendererText(), text=0)
        col.set_sort_column_id(0)
        col.set_sort_order(gtk.SORT_ASCENDING)
        self.tv_products.append_column(col)

        col = gtk.TreeViewColumn(_("Subscription Status"), gtk.CellRendererText(), text=1)
        col.set_sort_column_id(1)
        col.set_sort_order(gtk.SORT_ASCENDING)
        self.tv_products.append_column(col)

        col = gtk.TreeViewColumn(_("Expires"), gtk.CellRendererText(), text=2)
        col.set_sort_column_id(2)
        col.set_sort_order(gtk.SORT_ASCENDING)
        self.tv_products.append_column(col)

        self.productList.set_sort_column_id(0, gtk.SORT_ASCENDING)
        self.selection = self.tv_products.get_selection()
        self.selection.connect('changed', self.on_selection)

    def on_selection(self, selection):
        items,iter = selection.get_selected()
        pname_selected = items.get_value(iter,0)
        desc = managerlib.getProductDescription(pname_selected)
        pdetails = self.subsxml.get_widget("textview_details")
        pdetails.get_buffer().set_text(desc)
        pdetails.set_cursor_visible(False)
        pdetails.show()

    def updateMessage(self):
        self.sumlabel = self.subsxml.get_widget("summaryLabel1")
        if self.warn_count:
            self.sumlabel.set_label(_("<b>%s products or subscriptions need your attention.\n\n</b>Add or Update subscriptions for products you are using.\n" % self.warn_count))
        else:
            self.sumlabel.set_label(_("Add or Update subscriptions for products you are using."))

    def onUnsubscribeAction(self, button):
        pass

class AddSubscriptionScreen:
    """
     Add subscriptions Widget screen
    """
    def __init__(self):
        self.selected = {}
        self.addxml = gtk.glade.XML(gladexml, "add_dialog", domain="subscription-manager")
        self.add_vbox = \
                        self.addxml.get_widget("add-dialog-vbox2")
        self.populateAvailableList()

        dic = { "on_close_clicked" : self.cancel,
                "on_import_cert_button_clicked"   : self.onImportPrepare,
                "on_add_subscribe_button_clicked"   : self.onSubscribeAction,
            }
        self.addxml.signal_autoconnect(dic)
        self.addWin = self.addxml.get_widget("add_dialog")
        self.addWin.connect("hide", self.cancel)

        self.addWin.show_all()

    def finish(self):
        self.addWin.hide()

    def cancel(self, button):
        self.addWin.hide()

    def onImportPrepare(self, button):
        self.addWin.hide()
        ImportCertificate()

    def onSubscribeAction(self, button):
        consumer = managerlib.check_registration()
        for product, state in self.selected.items():
            if state:
                try:
                    print "Binding: ", product
                    print UEP.bindByProduct(consumer, product)
                except:
                    # Subscription failed, continue with rest
                    continue

    def populateAvailableList(self):
        consumer = managerlib.check_registration()
        self.availableList = gtk.TreeStore(gobject.TYPE_BOOLEAN, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING)
        for product in managerlib.getAvailableEntitlements(UEP, consumer):
            self.availableList.append(None, [False] + product.values())
        self.tv_products =  self.addxml.get_widget("treeview_available")
        self.tv_products.set_model(self.availableList)


        cell = gtk.CellRendererToggle()
        cell.set_property('activatable', True)
        cell.connect('toggled', self.col_selected, self.availableList)

        column = gtk.TreeViewColumn(_('Select'), cell)
        column.add_attribute(cell, "active", 0)
        self.tv_products.append_column(column)

        col = gtk.TreeViewColumn(_("Product"), gtk.CellRendererText(), text=1)
        col.set_sort_column_id(1)
        col.set_sort_order(gtk.SORT_ASCENDING)
        self.tv_products.append_column(col)

        col = gtk.TreeViewColumn(_("Available Slots"), gtk.CellRendererText(), text=3)
        col.set_spacing(4)
        col.set_sort_column_id(2)
        self.tv_products.append_column(col)

        col = gtk.TreeViewColumn(_("Expires"), gtk.CellRendererText(), text=2)
        col.set_sort_column_id(3)
        self.tv_products.append_column(col)

        self.availableList.set_sort_column_id(1, gtk.SORT_ASCENDING) 

    def col_selected(self, cell, path, model):
        items, iter = self.tv_products.get_selection().get_selected()
        model[path][0] = not model[path][0]
        print "Toggle '%s' to: %s" % (model[path][1], model[path][0])
        self.selected[model.get_value(iter, 1)] = model.get_value(iter, 0)

    def _cell_data_toggle_func(self, tree_column, renderer, model, treeiter):
        renderer.set_property('visible', True)


class UpdateSubscriptionScreen:
    def __init__(self):
        self.updatexml = gtk.glade.XML(gladexml, "update_dialog", domain="subscription-manager")
        dic = { "on_close_clicked" : self.cancel,
                "on_import_cert_button_clicked" : self.onImportPrepare,
            }
        self.updatexml.signal_autoconnect(dic)
        self.updateWin = self.updatexml.get_widget("update_dialog")
        self.updateWin.connect("hide", self.cancel)
        self.updateWin.show_all()

    def cancel(self, button=None):
        self.updateWin.hide()

    def onImportPrepare(self, button):
        self.updateWin.hide()
        ImportCertificate()

    def populateUpdatesDialog(self):
        consumer = managerlib.check_registration()
        self.updatesList = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING)
        for product in managerlib.getAvailableEntitlements(UEP, consumer):
            self.updatesList.append(product.values())
        self.tv_products =  self.updatexml.get_widget("treeview_updates")
        self.tv_products.set_model(self.updatesList)

class ImportCertificate:
    """
     Import an Entitlement Certificate Widget screen
    """
    def __init__(self):
        self.importxml = gtk.glade.XML(gladexml, "import_dialog", domain="subscription-manager")
        self.add_vbox = \
                        self.importxml.get_widget("import_vbox")

        dic = { "on_close_import" : self.cancel,
                "on_import_cert_button2_clicked" : self.importCertificate,
            }
        self.importxml.signal_autoconnect(dic)
        self.importWin = self.importxml.get_widget("import_dialog")
        self.importWin.connect("hide", self.cancel)

        self.importWin.show_all()

    def cancel(self, button=None):
      self.importWin.hide()

    def importCertificate(self, button):
        fileChooser = self.importxml.get_widget("certificateChooserButton")
        src_cert_file = fileChooser.get_filename()
        if src_cert_file is None:
            errorWindow(_("You must select a certificate."))
            return False

        if not os.access(ENT_CONFIG_DIR, os.R_OK):
            os.mkdir(ENT_CONFIG_DIR)

        dest_file_path = os.path.join(ENT_CONFIG_DIR, os.path.basename(src_cert_file))
        if not os.path.exists(dest_file_path):
            shutil.copy(src_cert_file, dest_file_path)

        self.importWin.hide()

def unexpectedError(message, exc_info=None):
    message = message + "\n" + (_("This error shouldn't have happened. If you'd "
                                 "like to help us improve this program, please "
                                 "file a bug at bugzilla.redhat.com. Including "
                                 "the relevant parts of would be very "
                                 "helpful. Thanks!") )
    errorWindow(message)
    if exc_info:
        (etype, value, stack_trace) = exc_info

def callAndFilterExceptions(function, allowedExceptions, 
        disallowedExceptionMessage, errorHandler=unexpectedError):
    assert callable(function)
    allowedExceptions.append(SystemExit)
    try:
        return function()
    except:
        (exceptionType, exception, stackTrace) = sys.exc_info()
        if exceptionType in allowedExceptions:
            raise
        else:
            errorHandler(disallowedExceptionMessage, 
                    (exceptionType, exception, stackTrace))

def errorWindow(message):
    messageWindow.ErrorDialog(messageWindow.wrap_text(message))

def setArrowCursor():
    """Dummy function that will be overidden by rhn_register's standalone gui
    and firstboot in different ways.
    
    """
    pass

def setBusyCursor():
    """Dummy function that will be overidden by rhn_register's standalone gui
    and firstboot in different ways.
    
    """
    pass


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    if os.geteuid() != 0 :
        #rootWarning()
        sys.exit(1)

    gui = ManageSubscriptionPage()
    gtk.main()


if __name__ == "__main__":
    main()
