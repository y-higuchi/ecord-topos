#!/bin/bash

# usage:
# ./set_mirror_port.sh set <TARGET_IF> <VID> <MIRROR_IF>
# ./set_mirror_port.sh clear <VID> <MIRROR_IF>

function set_mirror_port() {
    TARGET_IF=$1
    VID=$2
    MIRROR_IF=$3
    sudo ovs-vsctl add-port ovs${VID} ${MIRROR_IF}
    sudo ovs-vsctl -- set bridge ovs${VID} mirrors=@m -- --id=@${TARGET_IF}.${VID} get Port ${TARGET_IF}.${VID} -- --id=@${MIRROR_IF} get Port ${MIRROR_IF} -- --id=@m create Mirror name=mirror_test select-dst-port=@${TARGET_IF}.${VID} select-src-port=@${TARGET_IF}.${VID} output-port=@${MIRROR_IF}
}

function clear_all_mirror_port() {
    VID=$1
    MIRROR_IF=$2
    sudo ovs-vsctl clear bridge ovs${VID} mirrors
    sudo ovs-vsctl del-port ${MIRROR_IF}
}

CMD=$1
if [ $CMD = "set" ]; then
    set_mirror_port $2 $3 $4
elif [ $CMD = "clear" ]; then
    clear_all_mirror_port $2 $3
fi
