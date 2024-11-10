#!/bin/bash
name_tail=${1}
ip_address=${2}
ssh root@${ip_address} 'apt install -y git'
ssh root@${ip_address} 'rm -rf /root/armbianbegin'
ssh root@${ip_address} 'git clone https://github.com/zmhhaha/armbianbegin.git /root/armbianbegin'
ssh root@${ip_address} 'bash /root/armbianbegin/debian_begin.sh start '${name_tail}' '${ip_address}'
