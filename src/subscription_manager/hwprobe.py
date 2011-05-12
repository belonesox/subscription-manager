#
# Module to probe Hardware info from the system
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
import signal
import re
import logging
import gettext
_ = gettext.gettext
import ethtool
import socket
import commands
import glob
import re
import platform

from subprocess import Popen, PIPE



# Exception classes used by this module.
# from later versions of subprocess, but not there on 2.4, so include our version
class CalledProcessError(Exception):
    """This exception is raised when a process run by check_call() or
    check_output() returns a non-zero exit status.
    The exit status will be stored in the returncode attribute;
    check_output() will also store the output in the output attribute.
    """
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
    def __str__(self):
        return "Command '%s' returned non-zero exit status %d" % (self.cmd, self.returncode)


log = logging.getLogger('rhsm-app.' + __name__)


class DmiInfo(object):

    def __init__(self):
        self.info = self.getDmiInfo()

    def getDmiInfo(self):
        import dmidecode
        dmiinfo = {}

        dmi_data = {
            "dmi.bios.": self._read_dmi(dmidecode.bios),
            "dmi.processor.": self._read_dmi(dmidecode.processor),
            "dmi.baseboard.": self._read_dmi(dmidecode.baseboard),
            "dmi.chassis.": self._read_dmi(dmidecode.chassis),
            "dmi.slot.": self._read_dmi(dmidecode.slot),
            "dmi.system.": self._read_dmi(dmidecode.system),
            "dmi.memory.": self._read_dmi(dmidecode.memory),
            "dmi.connector.": self._read_dmi(dmidecode.connector),
        }

        try:
            for tag, func in dmi_data.items():
                dmiinfo = self._get_dmi_data(func, tag, dmiinfo)
        except Exception, e:
            log.warn(_("Error reading system DMI information: %s"), e)
        return dmiinfo

    def _read_dmi(self, func):
        try:
            return func()
        except Exception, e:
            log.warn(_("Error reading system DMI information with %s: %s"), func, e)
            return None

    def _get_dmi_data(self, func, tag, ddict):
        for key, value in func.items():
            for key1, value1 in value['data'].items():
                if not isinstance(value1, str):
                    continue
                nkey = ''.join([tag, key1.lower()]).replace(" ", "_")
                ddict[nkey] = str(value1)

        return ddict


class Hardware:

    def __init__(self):
        self.allhw = {}

    def getUnameInfo(self):

        uname_data = os.uname()
        uname_keys = ('uname.sysname', 'uname.nodename', 'uname.release',
                      'uname.version', 'uname.machine')
        self.unameinfo = dict(zip(uname_keys, uname_data))
        self.allhw.update(self.unameinfo)
        return self.unameinfo

    def getReleaseInfo(self):
        distro_keys = ('distribution.name', 'distribution.version',
                       'distribution.id')
        self.releaseinfo = dict(zip(distro_keys, self.getDistribution()))
        self.allhw.update(self.releaseinfo)
        return self.releaseinfo

    
    def _open_release(self, filename):
        return open(filename, 'r')

    # this version os very RHEL/Fedora specific...
    def getDistribution(self):

        if hasattr(platform, 'linux_distribution'):
            return platform.linux_distribution()

        # from platform.py from python2.
        _lsb_release_version = re.compile(r'(.+)'
                                          ' release '
                                          '([\d.]+)'
                                          '[^(]*(?:\((.+)\))?')
        f = self._open_release('/etc/redhat-release')
        firstline = f.readline()
        f.close()

        version = "unknown"
        distname = "unknown"
        id = "unknown"

        m = _lsb_release_version.match(firstline)

        if m is not None:
            return tuple(m.groups())

        return distname, version, id

    def getMemInfo(self):
        self.meminfo = {}

        # most of this mem info changes constantly, which makes decding
        # when to update facts painful, so lets try to just collect the
        # useful bits

        useful = ["MemTotal", "SwapTotal"]
        try:
            parser = re.compile(r'^(?P<key>\S*):\s*(?P<value>\d*)\s*kB')
            memdata = open('/proc/meminfo')
            for info in memdata:
                match = parser.match(info)
                if not match:
                    continue
                key, value = match.groups(['key', 'value'])
                if key in useful:
                    nkey = '.'.join(["memory", key.lower()])
                    self.meminfo[nkey] = "%s" % int(value)
        except:
            print _("Error reading system memory information:"), sys.exc_type
        self.allhw.update(self.meminfo)
        return self.meminfo

    def _getSocketIdForCpu(self, cpu):
        physical_package_id = "%s/topology/physical_package_id" % cpu
        f = open(physical_package_id)
        socket_id = f.readline()
        return socket_id

    def getCpuInfo(self):
        # TODO:(prad) Revisit this and see if theres a better way to parse /proc/cpuinfo
        # perhaps across all arches
        self.cpuinfo = {}
        sys_cpu = "/sys/devices/system/cpu/"

        # we also have cpufreq, etc in this dir, so match just the numbs
        cpu_re = r'cpu([0-9]+$)'

        cpu_files = []
        sys_cpu_path = "/sys/devices/system/cpu/"
        for cpu in os.listdir(sys_cpu_path):
            if re.match(cpu_re, cpu):
                cpu_files.append("%s/%s" % (sys_cpu_path,cpu))

        cpu_count = 0
        socket_count = 0
        thread_count = 0
        numa_count = 0

        socket_dict = {}
        numa_node_dict = {}
        for cpu in cpu_files:
            cpu_count = cpu_count + 1
            socket_id = self._getSocketIdForCpu(cpu)
            if socket_id not in socket_dict:
                socket_dict[socket_id] = 1
            else:
                socket_dict[socket_id] = socket_dict[socket_id] + 1

        self.cpuinfo['cpu.cpu_socket(s)'] = len(socket_dict)
        self.cpuinfo['cpu.core(s)_per_socket'] = cpu_count/len(socket_dict)
        self.cpuinfo["cpu.cpu(s)"] = cpu_count
        self.allhw.update(self.cpuinfo)
        return self.cpuinfo

    def getLsCpuInfo(self):
        # if we have `lscpu`, let's use it for facts as well, under
        # the `lscpu` name space

        if not os.access('/usr/bin/lscpu', os.R_OK):
            return

        self.lscpuinfo = {}
        try:
            cpudata = commands.getstatusoutput('LANG=en_US.UTF-8 /usr/bin/lscpu')[-1].split('\n')
            for info in cpudata:
                key, value = info.split(":")
                nkey = '.'.join(["lscpu", key.lower().strip().replace(" ", "_")])
                self.lscpuinfo[nkey] = "%s" % value.strip()
        except:
            print _("Error reading system cpu information:"), sys.exc_type
        self.allhw.update(self.lscpuinfo)
        return self.lscpuinfo

    def getNetworkInfo(self):
        self.netinfo = {}
        try:
            self.netinfo['network.hostname'] = socket.gethostname()
            try:
                self.netinfo['network.ipaddr'] = socket.gethostbyname(self.netinfo['network.hostname'])
            except:
                self.netinfo['network.ipaddr'] = "127.0.0.1"
        except:
            print _("Error reading networking information:"), sys.exc_type
        self.allhw.update(self.netinfo)
        return self.netinfo

    def getNetworkInterfaces(self):
        netinfdict = {}
        metakeys = ['hwaddr', 'ipaddr', 'netmask', 'broadcast']
        try:
            for interface in ethtool.get_devices():
                for mkey in metakeys:
                    key = '.'.join(['net.interface', interface, mkey])
                    try:
                        netinfdict[key] = getattr(
                                            ethtool, 'get_' + mkey)(interface)
                    except:
                        netinfdict[key] = "unknown"
        except:
            print _("Error reading net Interface information:"), sys.exc_type
        self.allhw.update(netinfdict)
        return netinfdict

    def getVirtInfo(self):
        virt_dict = {}

        try:
            host_type = self._get_output('virt-what')
            virt_dict['virt.host_type'] = host_type

            # If this is blank, then not a guest
            virt_dict['virt.is_guest'] = bool(host_type)
        # TODO:  Should this only catch OSErrors?
        except:
            # Otherwise there was an error running virt-what - who knows
            virt_dict['virt.is_guest'] = 'Unknown'

        self.allhw.update(virt_dict)
        return virt_dict

    def _get_output(self, cmd):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

        process = Popen([cmd], stdout=PIPE)
        output = process.communicate()[0].strip()

        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        returncode = process.poll()
        if returncode:
            raise CalledProcessError(returncode, cmd, output=output)

        return output

    def getPlatformSpecificInfo(self):
        """
        Read and parse data that comes from platform specific interfaces.
        This is only dmi/smbios data for now (which isn't on ppc/s390).
        """

        no_dmi_arches = ['ppc', 'ppc64', 's390', 's390x']
        arch = platform.machine()
        if arch in no_dmi_arches:
            log.debug("not looking for dmi info due to system arch '%s'" % arch)
            platform_specific_info = {}
        else:
            platform_specific_info = DmiInfo().info
        self.allhw.update(platform_specific_info)

    def getAll(self):
        hardware_methods  = [self.getUnameInfo,
                             self.getReleaseInfo,
                             self.getMemInfo,
                             self.getCpuInfo,
                             self.getLsCpuInfo,
                             self.getNetworkInfo,
                             self.getNetworkInterfaces,
                             self.getVirtInfo,
                             self.getPlatformSpecificInfo]
        # try each hardware method, and try/except around, since
        # these tend to be fragile
        for hardware_method in hardware_methods:
            try:
                hardware_method()
            except Exception, e:
                log.warn("Hardware detection failed: %s" % e)

        return self.allhw


if __name__ == '__main__':
    for hkey, hvalue in Hardware().getAll().items():
        print "'%s' : '%s'" % (hkey, hvalue)

