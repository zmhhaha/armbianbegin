#!/bin/bash
password=${1:-1234}
ssh-keygen -t rsa -b 2048 -N ""
touch ~/.ssh/authorized_keys
sshpass -p ${password} ssh-copy-id -o StrictHostKeyChecking=no nanopct4-master
sshpass -p ${password} ssh-copy-id -o StrictHostKeyChecking=no nanopct4-server1
sshpass -p ${password} ssh-copy-id -o StrictHostKeyChecking=no nanopct4-server2