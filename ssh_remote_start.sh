#!/bin/bash
ip_address=${1}
option=${2:-restart}
name_tail=${3}
static_ip_address=${4}
ssh root@${ip_address} 'apt install -y git'
ssh root@${ip_address} 'rm -rf /root/armbianbegin'
ssh root@${ip_address} 'git clone https://github.com/zmhhaha/armbianbegin.git /root/armbianbegin'
ssh root@${ip_address} 'bash /root/armbianbegin/debian_begin.sh '${option}' '${name_tail}' '${static_ip_address}'
