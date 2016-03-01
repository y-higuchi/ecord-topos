#!/usr/bin/env python
import json

from mininet.net import Mininet
from mininet.node import UserSwitch, OVSBridge, DefaultController, RemoteController, Host
from mininet.topo import Topo
from mininet.log import  setLogLevel, info, error, warn
from mininet.cli import CLI
from mininet.link import OVSIntf
from mininet.util import quietRun
from mininet.examples.vlanhost import VLANHost
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
            #uncomment to attach hosts onto leaf 
            #for h in range(f):
            #    self.s2gw[leaf] = '10.%s.%s.254' % (self.getId(), sw+1)
            #    host = self.addHost('h%s%s%s' % (self.getId(), sw, f+h+1), cls=IpHost,
            #                        ip='10.%s.%s.%s/24' % (self.getId(), sw+1, (f+h+1)),
            #                        gateway=self.s2gw[leaf])
            #    self.addLink(host, leaf)
            #    l_h.append(host)

        # interconnect spines and leaves.
        for spine in l_nsw:
            for leaf in l_msw:
                self.addLink(spine, leaf)

        # add normal mode OVS + host to EE-side leaf
        ee = 'leaf%s01' % self.getId()
        ovs = self.addSwitch('ovs%s000' % self.getId(), cls=OVSBridge)
        self.addLink(ovs, ee)
        # if standalone VNF host is needed - uncomment next two lines
        # vnf = self.addHost('h%s004' % self.getId() )
        # self.addLink(ovs, vnf)

        # add another EE CpQD + host to EE leaf
        #cpqd = self.addSwitch('ee%s001' % self.getId(),
        #                      cls=UserSwitch, dpopts='--no-local-port')
        cpqd = self.addHost('h111', cls=VLANHost )
        self.addLink(cpqd, ee)
        # if standalone customer host is needed - uncomment next two lines
        # cust = self.addHost('h%s005' % self.getId() )
        # self.addLink(cpqd, cust)

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

def attachDev(net, sw, dev):
    switch = net.get(sw)
    if hasattr(switch, "attach"):
        switch.attach(dev)
    else:
        switch.cmd('ip link set %s netns %s' % (dev, switch.pid))
    info("Interface %s is attached to switch %s.\n" % (dev, sw))

def setup(argv):
    ctls = sys.argv[1].split(',')
    ifs = sys.argv[2].split(',') if len(sys.argv) == 2 else []
    co = CO(1)
    for i in range (len(ctls)):
        co.addController('c%s' % i, controller=RemoteController, ip=ctls[i])

    # make/setup Mininet object
    net = Mininet()
    co.build()
    co.injectInto(net)
    #co.dumpCfg('co.json')

    # add external ports - hard-codedish
    for i in ifs:
        attachDev(net, 'leaf102', i)
    # start everything
    net.build()
    co.start()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    import sys
    if len(sys.argv) < 1:
        print ('Usage: sudo -E ./co.py [ctrls] [interfaces]\n\n',
               '[ctrls] : a comma-separated list of controller IPs\n',
               '[interfaces] : a comma-separated list of interfaces to the world (optional)')
    else:
        setup(sys.argv)
