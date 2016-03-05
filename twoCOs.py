#!/usr/bin/env python
"""
CORD-style central offices with default 2x2 (nxm) fabrics.

Each have:
- an unique id, <x>
- a xc<x>-eth0 interface to attach to a cross-connect VM
- a customer-facing leaf<x>01 that is also the endpoint of xc<x>-eth0
- a leaf<x>0<m> with a connection to an external interface.
"""

import json

from mininet.net import Mininet
from mininet.node import UserSwitch, OVSBridge, RemoteController, Host
from mininet.topo import Topo
from mininet.log import  setLogLevel, info, error, warn
from mininet.cli import CLI
from mininet.link import OVSIntf, Intf
from mininet.util import quietRun, errRun
from mininet.examples.vlanhost import VLANHost
from domains import SegmentRoutedDomain

class CO(SegmentRoutedDomain):


    def __init__(self, did):
        SegmentRoutedDomain.__init__(self, did, self.toCfg, False)
        self.vlans = {}
        self.s2gw = {}

    def addVLANNode(self, name, vlan):
        """Add a VLAN traffic source"""
        self.vlans[name] = vlan
        vip='10.0.%d.%d' % (self.getId(), len(self.vlans))
        return self.addHost(name, cls=VLANHost, vlan=vlan, ip=vip)

    def build(self, n=2, m=2):
        """
        bipartite graph, where n = spine; m = leaf; f = host fanout
        """
        opts='--no-local-port --no-slicing'
        l_nsw=[]
        l_msw=[]
        l_h=[]

        # create n spine switches.
        for sw in range(n):
            l_nsw.append(self.addSwitch('spine%s%s' % (self.getId(), sw+1),
                         cls=UserSwitch, dpopts=opts))

        # create m leaf switches, add f hosts.
        for sw in range(m):
            leaf = self.addSwitch('leaf%s0%s' % (self.getId(), sw+1),
                                  cls=UserSwitch, dpopts=opts)
            l_msw.append(self.noteLeaf(leaf))

        # last leaf is the tether.
        self.addTether(l_msw[-1])
 
        # interconnect spines and leaves
        for spine in l_nsw:
            for leaf in l_msw:
                self.addLink(spine, leaf)

        # add VLAN-aware host to EE-side leaf
        ee = 'leaf%s01' % self.getId()
        cpqd = self.addVLANNode('h%s11' % self.getId(), 100)
        self.addLink(cpqd, ee)

    def bootstrap(self, net, ifs):
        """ Do post-build, pre-start work """
        xc='xc%s-eth0' % self.getId()
        leaf='leaf%s01-eth0' % self.getId()

        # set EE MAC/IP. fix this so it can take more than 10 VLANs.
        i=0
        print(self.vlans)
        for name, vlan in self.vlans.iteritems():
            print(self.getHosts())
            ee = self.getHosts(name)
            ee.setMAC(self.getMAC('%01d1' % i, '11'))
            quietRun('vconfig add %s %s' % (xc, vlan))
            i+=1

        # add the ports that we will use as VxLAN endpoints
        errRun('ip link add %s type veth peer name %s' % (xc, leaf))
        quietRun('ifconfig %s hw ether %s' % (xc, self.getMAC('10', '01')))
        quietRun('ifconfig %s hw ether %s' % (leaf, self.getMAC('01', '01')))
        attachDev(net, 'leaf%s01' % self.getId(), leaf)
        quietRun('ifconfig %s up' % xc)
        quietRun('ifconfig %s up' % leaf)

        # attach outside interfaces
        for i in ifs:
            attachDev(net, self.getTether(), i)

    def toCfg(self):
        """ Dump a file in segment routing config file format. """
        i = 1
        for sw in self.getSwitches():
            if sw.name in self.getLeaves():
                swid = self.addSwitchCfg(sw, '%s0%s' % (self.getId(), i),
                                         self.s2gw[sw.name],
                                         '00:00:00:%02x:%02x:80' % (self.getId(), i))
                # check for non-loopback ports facing a host with name of form 'h.*'.
                for iface in filter(lambda el: el.name != 'lo', sw.intfList()):
                    ep1, ep2 = iface.link.intf1.node, iface.link.intf2.node

                    if (ep1.name[0] == 'h' or ep2.name[0] == 'h' or
                        'tether' in ep1.name or 'tether' in ep2.name):
                        ifid = self.addPortCfg(sw, iface)
                        self.intfCfg(ifid, [self.s2gw[sw.name] + '/24'])
            else:
                self.addSwitchCfg(sw, '%s0%s' % (self.getId(), i),
                                  '192.168.%s.%s' % (self.getId(), i),
                                  '00:00:00:%02x:%02x:80' % (self.getId(), i))
            i = i+1
        for h in self.getHosts():
            self.addHostCfg(h)

    def getMAC( self, unqf1, unqf2 ):
        """Make MAC addresses based on supplied unique values and domain ID for
           indexes 3, 4, and 5. The vaues should be supplied as strigs i.e.
           '00' or '02'."""
        n_mac = '02:ff:0a:%s:%s:%02x' % (unqf1, unqf2, self.getId())
        return n_mac

class IpHost(Host):
    def __init__(self, name, gateway, *args, **kwargs):
        super(IpHost, self).__init__(name, *args, **kwargs)
        self.gateway = gateway

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        mtu = "ifconfig "+self.name+"-eth0 mtu 1490"
        self.cmd(mtu)
        self.cmd('ip route add default via %s' % self.gateway)

def attachDev(net, sw, dev):
    switch = net.get(sw)
    if hasattr(switch, "attach"):
        switch.attach(dev)
    else:
        # not a dynamically configurable node.
        # manually move to namespace and add port to switch
        switch.cmd('ip link set %s netns %s' % (dev, switch.pid))
        Intf(dev, node=switch)
    info("Interface %s is attached to switch %s.\n" % (dev, sw))

def setup(argv):
    did = sys.argv[1]
    ctls = sys.argv[2].split(',')
    ifs = sys.argv[3].split(',') if len(sys.argv) > 2 else []
    co = CO(1)
    co2 = CO(2)
    for i in range (len(ctls)):
        co.addController('c%s' % i, controller=RemoteController, ip=ctls[i])
        co2.addController('c%s' % i, controller=RemoteController, ip=ctls[i])

    # make/setup Mininet object
    net = Mininet()
    co.build()
    co2.build()
    co.injectInto(net)
    co2.injectInto(net)
    #co.dumpCfg('co.json')
    co.bootstrap(net, ifs)
    co2.bootstrap(net, [])

    # start everything
    net.build()
    co.start()
    co2.start()

    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    import sys
    if len(sys.argv) < 2:
        print ('Usage: sudo -E ./co.py [domainID] [ctrls] [interfaces]\n\n',
               '[domainID] : a unique ID for this domain\n'
               '[ctrls] : a comma-separated list of controller IPs\n',
               '[interfaces] : a comma-separated list of interfaces to the world (optional)')
    else:
        setup(sys.argv)
