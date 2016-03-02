#!/usr/bin/env python
import json

from mininet.net import Mininet
from mininet.node import UserSwitch, DefaultController, RemoteController, Host
from mininet.topo import Topo
from mininet.log import  setLogLevel, info, error, warn
from mininet.cli import CLI
from mininet.link import OVSIntf
from mininet.util import quietRun

from domains import SegmentRoutedDomain

class CO(SegmentRoutedDomain):

    def __init__(self, did, ovs=False):
        SegmentRoutedDomain.__init__(self, did, self.toCfg, ovs)
        self.s2gw = {}
    
    def build(self, n=2, m=2, f=2):
        """
        bipartite graph, where n = spine; m = leaf; f = host fanout
        """
        l_nsw=[]
        l_msw=[]
        l_h=[]

        # create n spine switches.
        for sw in range(n):
            l_nsw.append(self.addSwitch('spine%s%s' % (self.getId(), sw+1),
                         cls=UserSwitch, dpopts='--no-local-port'))

        # create m leaf switches, add f hosts.
        for sw in range(m):
            leaf = self.addSwitch('leaf%s0%s' % (self.getId(), sw+1),
                                  cls=UserSwitch, dpopts='--no-local-port')
            l_msw.append(self.noteLeaf(leaf))
            for h in range(f):
                self.s2gw[leaf] = '10.%s.%s.254' % (self.getId(), sw+1)
                host = self.addHost('h%s%s%s' % (self.getId(), sw, f+h+1), cls=IpHost,
                                    ip='10.%s.%s.%s/24' % (self.getId(), sw+1, (f+h+1)),
                                    gateway=self.s2gw[leaf])
                self.addLink(host, leaf)
                l_h.append(host)

        # add extra intra-fabric sanity-test host to fabric gateway switch
        fgw = m-1
        host = self.addHost('h%s%s%s' % (self.getId(), fgw, f+f+1), cls=IpHost,
                            ip='10.%s.%s.%s/24' % (self.getId(), fgw+1, (f+f+1)),
                            gateway=self.s2gw[l_msw[fgw]])
        self.addLink(host, l_msw[fgw])
        l_h.append(host)
        

        # interconnect spines and leaves.
        for spine in l_nsw:
            for leaf in l_msw:
                self.addLink(spine, leaf)

    def toCfg(self):
        """ Dump a file in segment routing config file format. """
        i = 1
        for sw in self.getSwitches():
            if sw.name in self.getLeaves():
                swid = self.addSwitchCfg(sw, '%s0%s' % (self.getId(), i),
                                         self.s2gw[sw.name],
                                         '00:00:00:0%s:0%s:80' % (self.getId(), i))
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
                                  '00:00:00:0%s:0%s:80' % (self.getId(), i))
            i = i+1
        for h in self.getHosts():
            self.addHostCfg(h)

class IpHost(Host):
    def __init__(self, name, gateway, *args, **kwargs):
        super(IpHost, self).__init__(name, *args, **kwargs)
        self.gateway = gateway

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        mtu = "ifconfig "+self.name+"-eth0 mtu 1490"
        self.cmd(mtu)
        self.cmd('ip route add default via %s' % self.gateway)

def setup(argv):
    ctls = sys.argv[1].split(',')
    co = CO(1)
    for i in range (len(ctls)):
        co.addController('c%s' % i, controller=RemoteController, ip=ctls[i])

    # make/setup Mininet object
    net = Mininet()
    co.build()
    co.injectInto(net)
    co.dumpCfg('co.json')

    # start everything
    net.build()
    co.start()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    import sys
    if len(sys.argv) < 2:
        print ("Usage: sudo -E ./co.py ctl-set\n\n",
                "Where ctl-set is a comma-separated list of controller IP's")
    else:
        setup(sys.argv)
