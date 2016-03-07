# Steps for running co(2).py, with flow and cross-connect setup.
# example steps run on ecord2, with bridged external interface eth1.

# 1. in one window start topology - point to real ONOS in time.
sudo -s
./twoCOs.py 1:127.0.0.1:100:eth1
# if using co2.py (old script)
# python ./co2.py 127.0.0.1 eth1

# 2. program fabric path from host to eth1
./dpctl-cmds
# if pointing to domain n: ./dpctl-cmds n

# attach cross connect VM here?

# are the following below needed? Update based on VM configs
## On cross-connect OVS 
# ifconfig ovs1001-eth0 up
# ifconfig ovs1001-eth0.100 up

#  4. configure VxLAN
# ./ovs_vxlan.sh add ovs-1001 1001 1 <remoteIP> <localIP>
