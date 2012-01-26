#!/bin/env python

from twisted.internet import epollreactor
epollreactor.install()

from twisted.internet import reactor
from twisted.python import log
from OpenSSL import SSL
import sys

from epp import server

class ServerContextFactory:
	def __init__(self, certificate_file, privatekey_file, cafile=False):
		self.cf = certificate_file
		self.kf = privatekey_file
		self.ca = cafile
	def getContext(self):
		ctx = SSL.Context(SSL.SSLv23_METHOD)
		ctx.use_certificate_file(self.cf)
		ctx.use_privatekey_file(self.kf)
		if self.ca: ctx.load_verify_locations(self.ca)
		return ctx

crtfile = "/var/tmp/epp.crt"
keyfile = "/var/tmp/epp.key"
cafile  = "/etc/pki/tls/certs/ca-bundle.crt"

clientopts = {
#	"host": "epp-ote.verisign-grs.com",
#	"host": "epp.verisign-grs.com",
	"host": "localhost",
#	"port": 700,
	"port": 3200,
	"timeout": 5,
#	"sslctx": ServerContextFactory(crtfile, keyfile, cafile)
#	"keepalive_interval": 5*60
#	"max_lifetime": 8*60*60,
}

log.startLogging(sys.stdout)
f = server.EPPProxyServerFactory(clientopts, max_clients=2, max_retries=1)
reactor.listenTCP(3232, f)
reactor.run()

