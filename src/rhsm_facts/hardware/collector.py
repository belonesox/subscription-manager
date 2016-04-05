# Copyright (c) 2011-2015 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#

from rhsm_facts.hardware import hwprobe
from rhsm_facts.hardware import network
from rhsm_facts.hardware import cpuinfo
from rhsm_facts.hardware import memory


class HardwareCollector(object):
    def __init__(self):
        self.facts = {}

    def collect(self, collected_facts=None):
        new_facts = hwprobe.Hardware().get_all()
        collected_facts.update(new_facts)

        network_facts = network.Network().collect(collected_facts)
        collected_facts.update(network_facts)

        # FIXME: updating dict in the collecter, returning the whole
        #        dict, then updating it with itself
        cpuinfo_facts = cpuinfo.Cpuinfo().collect(collected_facts)
        collected_facts.update(cpuinfo_facts)

        memory_facts = memory.Memory().collect(collected_facts)
        collected_facts.update(memory_facts)

        return collected_facts
