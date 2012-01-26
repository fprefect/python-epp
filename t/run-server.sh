#!/bin/sh

BASE="/home/dev/python-epp"

env PYTHONPATH=$BASE twistd -o -n epp-rproxy -c $BASE/etc/epp-test.conf
