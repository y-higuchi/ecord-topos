# ecord-topos
Sample Mininet scripts for metro area networks. 

Requires setup as follows:
https://wiki.onosproject.org/display/ONOS/Metro+Network+Emulation

- domains.py : wrapper for creating network domains controlled by their own controller(s)
- metro.py : four-domain internetwork with three COs ( CPqD leaf-spines ) connected to three metro core switches (LINC nodes) via OVS.
- co.py : a 2x2 leaf-spine fabric (CO) with two hosts per leaf. Doesn't require LINC. 
- ectest.py : standalone internetwork with two simplified COs ( an OVS and a CpQD ) interconnected by an optical core of three LINC nodes.
