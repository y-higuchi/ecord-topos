#!/bin/bash

# usage:
# ./ovs_vxlan.sh add <interface> <vlan_vid> <vxlan_vni> <vxlan_remote_ip>
# ./ovs_vxlan.sh delete <interface> <vlan_vid> <vxlan_vni>


CMD=$1
IF=$2
VID=$3
VNI=$4
REMOTE_IP=$5

function add_config() {
    IF=$1
    VID=$2
    VNI=$3
    REMOTE_IP=$4

    sudo vconfig add $IF $VID
    sudo ip link set $IF.$VID promisc on
    sudo ovs-vsctl add-br ovs$VID
    sudo ovs-vsctl add-port ovs$VID $IF.$VID
    sudo ovs-vsctl add-port ovs$VID vxlan$VNI -- set interface vxlan$VNI type=vxlan options:key=$VNI options:remote_ip=$REMOTE_IP
}

function delete_config() {
    IF=$1
    VID=$2
    VNI=$3

    sudo ovs-vsctl del-port vxlan$VNI
    sudo ovs-vsctl del-port $IF.$VID
    sudo ovs-vsctl del-br ovs$VID
    sudo vconfig rem $IF.$VID
}

if [ $CMD = "add" ]; then
    add_config $IF $VID $VNI $REMOTE_IP
elif [ $CMD = "delete" ]; then
    delete_config $IF $VID $VNI
fi
