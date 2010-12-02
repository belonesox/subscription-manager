# Subscription Manager Compliance Assistant
#
# Copyright (c) 2010 Red Hat, Inc.
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
import gtk
import gobject
import locale
import logging
import gettext
from datetime import date, time, datetime

_ = gettext.gettext

from logutil import getLogger
log = getLogger(__name__)

import certificate
import certlib
from certlib import find_last_compliant, CertSorter
import managerlib
import storage
import widgets
import progress
from connection import RestlibException
from utils import handle_gui_exception


prefix = os.path.dirname(__file__)
COMPLIANCE_GLADE = os.path.join(prefix, "data/compliance.glade")


class MappedListTreeView(gtk.TreeView):

    def add_toggle_column(self, name, column_number, callback):
        toggle_renderer = gtk.CellRendererToggle()
        toggle_renderer.set_property("activatable", True)
        toggle_renderer.set_radio(False)
        toggle_renderer.connect("toggled", callback)
        column = gtk.TreeViewColumn(name, toggle_renderer, active=column_number)
        self.append_column(column)

    def add_column(self, name, column_number, expand=False):
        text_renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(name, text_renderer, text=column_number)
        self.store = self.get_model()
        if expand:
            column.set_expand(True)
        else:
            column.add_attribute(text_renderer, 'xalign', self.store['align'])

#        column.add_attribute(text_renderer, 'cell-background',
#                             self.store['background'])

        self.append_column(column)

    def add_date_column(self, name, column_number, expand=False):
        date_renderer = widgets.CellRendererDate()
        column = gtk.TreeViewColumn(name, date_renderer, text=column_number)
        self.store = self.get_model()
        if expand:
            column.set_expand(True)
        else:
            column.add_attribute(date_renderer, 'xalign', self.store['align'])

        self.append_column(column)

class ComplianceAssistant(object):

    """ Compliance Assistant GUI window. """
    def __init__(self, backend, consumer, facts):
        self.backend = backend
        self.consumer = consumer
        self.facts = facts
        self.pool_stash = managerlib.PoolStash(self.backend, self.consumer,
                self.facts)

        self.product_dir = certlib.ProductDirectory()
        self.entitlement_dir = certlib.EntitlementDirectory()
        self.cached_date = None

        self.compliance_xml = gtk.glade.XML(COMPLIANCE_GLADE)
        self.compliance_label = self.compliance_xml.get_widget(
                'compliance_label')
        self.compliant_today_label = self.compliance_xml.get_widget(
                'compliant_today_label')
        self.providing_subs_label = self.compliance_xml.get_widget(
                'providing_subs_label')

        # Setup initial last compliant date:
        self.last_compliant_date = find_last_compliant()
        self.noncompliant_date_radiobutton = self.compliance_xml.get_widget(
                "noncompliant_date_radiobutton")


        uncompliant_type_map = {'active':bool,
                                'product_name':str,
                                'contract':str,
                                'end_date':str,
                                'entitlement_id':str,
                                'product_id':str,
                                'entitlement':gobject.TYPE_PYOBJECT,
                                'align':float}

        self.window = self.compliance_xml.get_widget('compliance_assistant_window')
        self.window.connect('delete_event', self.hide)
        self.uncompliant_store = storage.MappedListStore(uncompliant_type_map)
        self.uncompliant_treeview = MappedListTreeView(self.uncompliant_store)

        self.uncompliant_treeview.add_toggle_column(None,
                                                    self.uncompliant_store['active'],
                                                    self._on_uncompliant_active_toggled)
        self.uncompliant_treeview.add_column("Product",
                self.uncompliant_store['product_name'], True)
        self.uncompliant_treeview.add_column("Contract",
                self.uncompliant_store['contract'], True)
        self.uncompliant_treeview.add_date_column("Expiration",
                self.uncompliant_store['end_date'], True)
        self.uncompliant_treeview.set_model(self.uncompliant_store)
        vbox = self.compliance_xml.get_widget("uncompliant_vbox")
        vbox.pack_end(self.uncompliant_treeview)
        self.uncompliant_treeview.show()

        subscriptions_type_map = {
            'product_name': str,
            'total_contracts': int,
            'total_subscriptions': int,
            'available_subscriptions': int,
            'pool_id': str, # not displayed, just for lookup
        }

        self.subscriptions_store = storage.MappedListStore(subscriptions_type_map)
        self.subscriptions_treeview = MappedListTreeView(self.subscriptions_store)
        self.subscriptions_treeview.add_column("Subscription Name",
                self.subscriptions_store['product_name'], True)
        self.subscriptions_treeview.add_column("Total Contracts",
                self.subscriptions_store['total_contracts'], True)
        self.subscriptions_treeview.add_column("Total Subscriptions",
                self.subscriptions_store['total_subscriptions'], True)
        self.subscriptions_treeview.add_column("Available Subscriptions",
                self.subscriptions_store['available_subscriptions'], True)

        self.subscriptions_treeview.set_model(self.subscriptions_store)
        self.subscriptions_treeview.get_selection().connect('changed',
                self._update_sub_details)

        vbox = self.compliance_xml.get_widget("subscriptions_vbox")
        vbox.pack_start(self.subscriptions_treeview)
        self.subscriptions_treeview.show()

        self.sub_details = widgets.SubDetailsWidget(show_contract=False)
        vbox.pack_start(self.sub_details.get_widget())

        self.first_noncompliant_radiobutton = \
            self.compliance_xml.get_widget('first_noncompliant_radiobutton')
        self.first_noncompliant_radiobutton.set_active(True)
        self.noncompliant_date_radiobutton = \
            self.compliance_xml.get_widget('noncompliant_date_radiobutton')

        
        self.date_picker = widgets.DatePicker(date.today())
        self.date_picker.connect('date-picked', self._compliance_date_selected)
        date_picker_hbox = self.compliance_xml.get_widget("date_picker_hbox")
        date_picker_hbox.pack_start(self.date_picker, False, False)
        self.date_picker.show_all()

        self.compliance_xml.signal_autoconnect({
            "on_first_noncompliant_radiobutton_toggled": self._check_for_date_change,
            "on_noncompliant_date_radiobutton_toggled": self._check_for_date_change,
        })

        self.pb = None
        self.timer = None

    def show(self):
        """
        Called by the main window when this page is to be displayed.
        """
        try:
            self._reload_screen()
            self.window.show()
        except RestlibException, e:
            handle_gui_exception(e, _("Error fetching subscriptions from server: %s"))
        except Exception, e:
            handle_gui_exception(e, _("Error displaying Compliance Assistant. Please see /var/log/rhsm/rhsm.log for more information."))

    def _reload_callback(self, compat, incompat, allsubs):
        if self.pb:
            self.pb.hide()
            gobject.source_remove(self.timer)
            self.pb = None
            self.timer = None

        self._display_uncompliant()
        self._display_subscriptions()

    def _reload_screen(self, widget=None):
        """
        Draws the entire screen, called when window is shown, or something
        changes and we need to refresh.
        """
        log.debug("reloading screen")
        log.debug("   widget = %s" % widget)
        # end date of first subs to expire

        self.last_compliant_date = find_last_compliant()

        noncompliant_date = self._get_noncompliant_date()
        log.debug("using noncompliance date: %s" % noncompliant_date)
        if self.last_compliant_date:
            formatted = self.format_date(self.last_compliant_date)
            self.compliance_label.set_label(
                    _("All software is in compliance until %s.") % formatted)
            self.first_noncompliant_radiobutton.set_label(
                    _("%s (first date of non-compliance)") % formatted)
            self.providing_subs_label.set_label(
                    _("The following subscriptions will cover the products selected on %s" % noncompliant_date.strftime("%x")))

        self.pool_stash.async_refresh(noncompliant_date, self._reload_callback)

        # show pulsating progress bar while we wait for results
        self.pb = progress.Progress(
                _("Searching for subscriptions. Please wait."))
        self.timer = gobject.timeout_add(100, self.pb.pulse)

    def _check_for_date_change(self, widget):
        """
        Called when the compliance date selection *may* have changed. 
        Several signals must be sent out to cover all situations and thus
        multiple may trigger at once. As such we need to store the 
        non-compliant date last calculated, and compare it to see if 
        anything has changed before we trigger an expensive refresh.
        """
        d = self._get_noncompliant_date()
        if self.cached_date != d:
            log.debug("New compliance date selected, reloading screen.")
            self.cached_date = d
            self._reload_screen()
        else:
            log.debug("No change in compliance date, skipping screen reload.")

    def _compliance_date_selected(self, widget):
        """
        Callback for the date selector to execute when the date has been chosen.
        """
        log.debug("Compliance date selected.")
        self.noncompliant_date_radiobutton.set_active(True)
        self._check_for_date_change(widget)

    def _get_noncompliant_date(self):
        """
        Returns a datetime object for the non-compliant date to use based on current
        state of the GUI controls.
        """
        if self.first_noncompliant_radiobutton.get_active():
            return self.last_compliant_date
        else:
            # Need to convert to a datetime:
            d = self.date_picker.date
            return datetime(d.year, d.month, d.day, tzinfo=certificate.GMT())

    def _display_uncompliant(self):
        """
        Displays the list of products or entitlements that will be out of
        compliance on the selected date.
        """
        sorter = CertSorter(self.product_dir, self.entitlement_dir,
                on_date=self._get_noncompliant_date())

        # These display the list of products uncompliant on the selected date:
        self.uncompliant_store.clear()

        # installed but not entitled products:
        na = _("N/A")
        for product in sorter.unentitled:
            self.uncompliant_store.add_map({
                'active': False,
                'product_name': product.getProduct().getName(),
                'contract': na,
                'end_date': na,
                'entitlement_id': None,
                'entitlement': None,
                'product_id': product.getProduct().getHash(),
                'align': 0.0
            })

        # installed and out of compliance
        for ent_cert in sorter.expired:
            self.uncompliant_store.add_map({
                'active': False,
                'product_name': ent_cert.getProduct().getName(),
                'contract': ent_cert.getOrder().getNumber(),
                # is end_date when the cert expires or the orders end date? is it differnt?
                'end_date': '%s' % self.format_date(ent_cert.validRange().end()),
                'entitlement_id': ent_cert.serialNumber(),
                'entitlement': ent_cert,
                'product_id': ent_cert.getProduct().getHash(),
                'align': 0.0
            })


    def _display_subscriptions(self):
        """
        Displays the list of subscriptions that will replace the selected
        products/entitlements that will be out of compliance.

        To do this, will will build a master list of all product IDs selected,
        both the top level marketing products and provided products. We then
        look for any subscription valid for the given date, which provides
        *any* of those product IDs. Note that there may be duplicate subscriptions
        shown. The user can select one subscription at a time to request an
        entitlement for, after which we will refresh the screen based on this new
        state.
        """
        self.subscriptions_store.clear()

        subscriptions_map = {}
        # this should be roughly correct for locally manager certs, needs
        # remote subs/pools as well

        # TODO: the above only hits entitlements, un-entitled products are not covered

        selected_products = self._get_selected_product_ids()
        pool_filter = managerlib.PoolFilter(self.product_dir, self.entitlement_dir)
        relevant_pools = pool_filter.filter_product_ids(
                self.pool_stash.all_pools.values(), selected_products)
        merged_pools = managerlib.merge_pools(relevant_pools).values()

        for entry in merged_pools:
            self.subscriptions_store.add_map({
                'product_name': entry.product_name,
                'total_contracts': len(entry.pools),
                'total_subscriptions': entry.quantity,
                'available_subscriptions': entry.quantity - entry.consumed,
                'pool_id': entry.pools[0]['id'],
            })


    def _get_selected_product_ids(self):
        """
        Builds a master list of all product IDs for the selected non-compliant
        products/entitlements. In the case of entitlements which will be expired,
        we assume you want to keep all provided products you have now, so these
        provided product IDs will be included in the list.
        """
        all_product_ids = []
        for row in self.uncompliant_store:
            if row[self.uncompliant_store['active']]:
                ent_cert = row[self.uncompliant_store['entitlement']]
                if not ent_cert:
                    # This must be a completely unentitled product installed, just add it's
                    # top level product ID:
                    # TODO: can these product certs have provided products as well?
                    all_product_ids.append(row[self.uncompliant_store['product_id']])
                else:
                    for product in ent_cert.getProducts():
                        all_product_ids.append(product.getHash())
        log.debug("Calculated all selected non-compliant product IDs:")
        log.debug(all_product_ids)
        return all_product_ids

    def _on_uncompliant_active_toggled(self, cell, path):
        """
        Triggered whenever the user checks one of the products/entitlements
        in the non-compliant section of the UI.
        """
        treeiter = self.uncompliant_store.get_iter_from_string(path)
        item = self.uncompliant_store.get_value(treeiter, self.uncompliant_store['active'])
        self.uncompliant_store.set_value(treeiter, self.uncompliant_store['active'], not item)

        # refresh subscriptions
        self._display_subscriptions()

    def format_date(self, date):
        return date.strftime(locale.nl_langinfo(locale.D_FMT))

    def hide(self, widget, event, data=None):
        self.window.hide()
        return True

    def _update_sub_details(self, widget):
        """ Shows details for the current selected pool. """
        model, tree_iter = widget.get_selected()
        if tree_iter:
            product_name = model.get_value(tree_iter, self.subscriptions_store['product_name'])
            pool_id = model.get_value(tree_iter, self.subscriptions_store['pool_id'])
            provided = self.pool_stash.lookup_provided_products(pool_id)
            self.sub_details.show(product_name, products=provided)
