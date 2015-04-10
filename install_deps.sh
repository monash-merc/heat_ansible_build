#!/bin/bash
sudo apt-get -y update
sudo apt-get -y install python-novaclient
sudo apt-get -y install git
sudo apt-get -y install python-setuptools
sudo apt-get -y install python-pip
sudo apt-get -y install python-dev
ORIG_PWD=`pwd`
cd ~
git clone https://github.com/ansible/ansible.git
cd ansible
sudo python setup.py install
cd ~
git clone https://github.com/openstack-dev/pbr.git
cd pbr
sudo python setup.py install
cd ~
git clone https://github.com/openstack/python-heatclient.git
cd python-heatclient
sudo python setup.py install
cd $ORIG_PWD
