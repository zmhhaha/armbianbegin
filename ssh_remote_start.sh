#!/bin/bash
ip_address=${1}
ssh root@${ip_address} 'apt install -y git'
ssh root@${ip_address} 'rm -rf /root/armbianbegin'
ssh root@${ip_address} 'git clone https://github.com/zmhhaha/armbianbegin.git /root/armbianbegin'
ssh root@${ip_address} 'bash /root/armbianbegin/debian_begin.sh'