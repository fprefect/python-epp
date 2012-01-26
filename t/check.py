#!/usr/bin/env python

from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory, ClientCreator
from twisted.python import log
import sys

from epp import client, protocol

username = "user"
password = "pass"
domain = "eppvalid.com"


class MyEPPTemplateFrame(protocol.EPPTemplateFrame):
	xml_login = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd"><command><login><clID>${user}</clID><pw>${pass}</pw><options><version>1.0</version><lang>en</lang></options><svcs><objURI>urn:ietf:params:xml:ns:domain-1.0</objURI><objURI>urn:ietf:params:xml:ns:host-1.0</objURI><svcExtension><extURI>http://www.verisign-grs.com/epp/namestoreExt-1.1</extURI><extURI>http://www.verisign.com/epp/sync-1.0</extURI><extURI>urn:ietf:params:xml:ns:rgp-1.0</extURI></svcExtension></svcs></login><clTRID>${clTRID}</clTRID></command></epp>'''

	xml_check = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd"><command><check><domain:check xmlns:domain="urn:ietf:params:xml:ns:domain-1.0" xsi:schemaLocation="urn:ietf:params:xml:ns:domain-1.0 domain-1.0.xsd"><domain:name>${domain}</domain:name></domain:check></check><extension><namestoreExt:namestoreExt xmlns:namestoreExt="http://www.verisign-grs.com/epp/namestoreExt-1.1" xsi:schemaLocation="http://www.verisign-grs.com/epp/namestoreExt-1.1 namestoreExt-1.1.xsd"><namestoreExt:subProduct>dotNET</namestoreExt:subProduct></namestoreExt:namestoreExt></extension><clTRID>${clTRID}</clTRID></command></epp>'''

class MyEPPClient(client.EPPClient):
	def serverGreeting(self, frame):
		self.dump_frames = False
		self.setTimeout(5)
		print "### Got greeting type:", frame.frameType()
		reactor.callLater(0, self.go)

	def go(self):
		d = self.doCmd(None, "Logging in", self.login, MyEPPTemplateFrame('login',{"user": username, "pass": password}))
		d.addCallback(self.doCmd, "Checking domain", self.command, MyEPPTemplateFrame('check',{"domain": domain}))
		d.addCallback(self.doCmd, "Logging out", self.logout)
		d.addCallback(lambda *_: self.transport.loseConnection())
		d.addErrback(self.ebproblem)
		d.addCallback(lambda *_: reactor.stop())
		
	def doCmd(self, frame, str, func, *args):
		if frame:
			print "### Response frame:", frame.frameType()
			if self.dump_frames:
				print "<<< Response frame:"
				print frame.xml
				print "<<<"
		print "###", str
		if self.dump_frames and len(args) > 0 and isinstance(args[0], protocol.EPPFrame):
			print ">>> Request Frame:"
			print args[0].xml
			print ">>>"
		return func(*args)
		
	def ebproblem(self, problem):
		print "!!! Error:", problem
		self.transport.loseConnection()

if __name__ == '__main__':
	log.startLogging(sys.stdout)
	d = ClientCreator(reactor, MyEPPClient).connectTCP('127.0.0.1', 8701)
	reactor.run()
