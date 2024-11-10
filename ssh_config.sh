#!/bin/bash
ssh-keygen -t rsa -b 2048 -f ~/.ssh/id_rsa -N ""
ssh-copy-id -o StrictHostKeyChecking=no nanopct4-master
ssh-copy-id -o StrictHostKeyChecking=no nanopct4-server1
ssh-copy-id -o StrictHostKeyChecking=no nanopct4-server2