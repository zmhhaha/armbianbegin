#!/bin/bash
hostnames="nanopct4-server1 nanopct4-server2"
IFS=' ' read -r -a hostnamearray <<< "$hostnames"
for i in "${hostnamearray[@]}"; do
    scp -r /certs/self_registry_ca.crt root@${i}:/certs/self_registry_ca.crt
    scp -r /certs/self_registry_ca.key root@${i}:/certs/self_registry_ca.key
    ssh root@${i} "cp /certs/self_registry_ca.crt /etc/ssl/certs/"
    ssh root@${i} "cp /certs/self_registry_ca.key /etc/ssl/certs/"
done