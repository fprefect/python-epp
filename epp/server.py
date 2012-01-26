
from twisted.python import log, failure
from twisted.internet import reactor, defer, protocol
from epp import client
from epp.protocol import EPP, EPPFrame, EPPTemplateFrame
import time
import logging
import re

class mylog():
	""" Simple workaround to have log levels in twisted plugin """
	mask = logging.INFO
	prefix = {logging.DEBUG: "DEBUG", logging.WARNING: "WARNING", logging.ERROR: "ERROR", logging.CRITICAL: "CRITICAL"}
	def msg(self, msg, **kw):
		logLevel = self.mask
		if 'logLevel' in kw:
			logLevel = kw['logLevel']
		if logLevel >= self.mask:
			if logLevel != logging.INFO:
				return log.msg("%s: %s" % (self.prefix[logLevel], msg), **kw)
			return log.msg(msg, **kw)

class EPPRequest():
	def __init__(self, frame):
		self.request = frame
		self.response = None
		self.retries = 0

class EPPProxyServer(EPP):

	log = mylog()

	def connectionMade(self):
		self.log.msg("Client connect " + str(self.transport.getPeer()))
		if "greeting" in self.factory.cache:
			self.sendFrame(self.factory.cache["greeting"].xml)
			return
		d = self.factory.client.getGreeting()
		d.addBoth(lambda m: self.sendResponse(m))

	def connectionLost(self, reason):
		self.log.msg("Client disconnect " + str(self.transport.getPeer()) + ", " + reason.getErrorMessage())

	def frameReceived(self, frame):	
		self.log.msg("REQUEST: "+frame.frameType(), logLevel=logging.DEBUG)
		req = EPPRequest(frame)
		self.filterRequest(req)
		if req.response:
			self.log.msg("Got response in filter, sending it to client", logLevel=logging.DEBUG)
			self.sendResponse(req)
			return
		d = self.setResponse(req)
		d.addCallback(self.filterResponse)
		d.addBoth(self.sendResponse)

	def filterRequest(self, req):
		reqtype = req.request.frameType()
		if reqtype == 'login':
			if "login" in self.factory.cache and self.factory.cache["login"].response:
				# No need to make sure authentication is good (or the same) since it's not require per connection
				self.log.msg("Using cached login response", logLevel=logging.DEBUG)
				req.response = self.factory.cache["login"].response
		elif reqtype == "logout":
			req.response = EPPTemplateFrame('logout_response')
		return req

	def filterResponse(self, req):
		if not "login" in self.factory.cache and req.request.frameType() == "login" and req.response.frameType() == "success":
			self.log.msg("Caching successful login response", logLevel=logging.DEBUG)
			self.factory.cache["login"] = req
		return req

	def sendResponse(self, m):
		if isinstance(m, EPPRequest):
			self.sendFrame(m.response)
			self.log.msg("RESPONSE: "+m.response.frameType(), logLevel=logging.DEBUG)
		elif isinstance(m, EPPFrame):
			self.sendFrame(m)
			self.log.msg("RESPONSE: "+m.frameType(), logLevel=logging.DEBUG)
		elif isinstance(m, failure.Failure):
			frame = EPPTemplateFrame('error', {'msg':m.getErrorMessage()})
			self.sendFrame(frame)
			self.log.msg("RESPONSE: "+frame.frameType(), logLevel=logging.DEBUG)
			return frame # Make sure we don't propogate the error beyond here.
		return m

	def setResponse(self, req):
		d = self.factory.client.getResponse(req.request)
		d.addBoth(self._setResponse, req)
		return d

	def _setResponse(self, m, req):
		if isinstance(m, EPPFrame):
			req.response = m
			return req

		# If we didn't get a proper response or a failure, create an error and continue
		# This shouldn't ever happen. Fix the bug.
		if not isinstance(m, failure.Failure):
			self.log.msg("BUG: Unknown type in _setResponse, repr(frame) == "+repr(m), logLevel=logging.ERROR)
			class UnexpectedResponseError(Exception):
				def __str__(self): return "Error: Unexpected response: "+repr(m)	
			m = failure.Failure(UnexpectedResponseError()) 

		self.log.msg("Failure was returned from self.factory.client.getResponse. retries=%d/%d, failure=%s" % 
			(req.retries, self.factory.max_retries, m), logLevel=logging.ERROR)

		# try again.
		if req.retries < self.factory.max_retries:
			req.retries += 1
			self.log.msg("Retrying frame. retries=%d" % (req.retries,), logLevel=logging.WARNING)
			d = self.factory.client.getResponse(req.request)
			d.addBoth(self._setResponse, req)
			return d
		return m

class ClientUnavailableError(Exception):
	def __str__(self): return "client unavailable"

class ClientPendingError(Exception):
	def __str__(self): return "client already pending"

class ClientLoginRequiredError(Exception):
	def __str__(self): return "client login required"

class EPPProxyClient(client.EPPClient):
	log = mylog()
	def __init__(self, timeout=0, keepalive_interval=0):
		self.greeting = None
		self.keepalive_interval = keepalive_interval
		self._ka_call = None
		client.EPPClient.__init__(self, timeout)
	def frameReceived(self, frame):
		#if self.keepalive_interval: reactor.callLater(0, self._keepaliveReset)
		if self.keepalive_interval: self._keepaliveReset()
		return client.EPPClient.frameReceived(self, frame)
	def connectionLost(self, reason):
		self.log.msg("Connection lost: "+str(reason), logLevel=logging.WARNING)
		return client.EPPClient.connectionLost(self, reason)
	def _keepaliveReset(self):
		if self._ka_call and self._ka_call.active():
			self._ka_call.cancel()
		self._ka_call = reactor.callLater(self.keepalive_interval, self._keepalive)	
	def _keepalive(self):
		if self.closed: return
		if not self.isReady:
			reactor.callLater(self.keepalive_interval, self._keepalive)
			return
		self.log.msg("Sending keepalive, "+str(self.transport.getPeer()))
		d = self.command(EPPTemplateFrame('hello'))
		d.addBoth(lambda *_: None) # discard response even if error
	def getGreeting(self):
		if self.greeting: 
			self.log.msg("Proxy client returning cached greeting", logLevel=logging.DEBUG)
			return defer.succeed(self.greeting)
		self._waiting = defer.Deferred()
		return self._waiting
	def serverGreeting(self, frame):
		self.log.msg("Proxy client received greeting from peer", logLevel=logging.DEBUG)
		self.greeting = frame
		if self.keepalive_interval: self._keepaliveReset()
		if self._waiting:
			self.log.msg("Proxy client calling back with greeting", logLevel=logging.DEBUG)
			d, self._waiting = self._waiting, None
			d.callback(self.greeting)

class EPPProxyClientPool():
	log = mylog()
	def __init__(self, server_factory, max_clients, clientopts):
		self.factory = server_factory
		self.clientopts = clientopts
		self.clients = []
		self.max_clients = max_clients

	def getGreeting(self):
		return self.getClient().addCallback(lambda p: p.getGreeting())

	def getResponse(self, frame):
		return self.getClient().addCallback(self._getResponse, frame)

	def _getResponse(self, p, frame):
		if p.logged_in:
			self.log.msg("Proxy client logged in, sending command: "+ frame.frameType(), logLevel=logging.DEBUG)
			d = p.command(frame)
		else:
			if frame.frameType() == 'login':
				self.log.msg("Proxy client not logged in but the frame type is login, so logging in", logLevel=logging.DEBUG)
				d = p.login(frame)
			else:
				if 'login' not in self.factory.cache:
					self.log.msg("Proxy client not logged in and frame type is not login and no login in cache. fail. frame type="+ frame.frameType(), logLevel=logging.ERROR)
					return defer.fail(ClientLoginRequiredError)
				self.log.msg("Proxy client not logged in but login frame in cache. using it.", logLevel=logging.DEBUG)
				d = p.login(self.factory.cache["login"].request)
				d.addCallback(lambda _: p.command(frame))
				#d.addCallback(self._sendAfterLogin, frame, p)
		return d

	def _sendAfterLogin(self, resp, frame, p):
		if(isinstance(resp, EPPFrame)):
			self.log.msg("Received login response: "+resp.frameType(), logLevel=logging.DEBUG)
		else:
			self.log.msg("Received login response: "+resp, logLevel=logging.DEBUG)
		self.log.msg("Sending command: "+frame.frameType(), logLevel=logging.DEBUG)
		d = p.command(frame)
		return d

	def newClient(self):
		c = protocol.ClientCreator(reactor, EPPProxyClient, 
								   timeout=self.clientopts.get("timeout",0), 
								   keepalive_interval=self.clientopts.get("keepalive_interval",0))
		if "sslctx" in self.clientopts:
			self.log.msg("Proxy Client connecting SSL with opts "+repr(self.clientopts))
			d = c.connectSSL(self.clientopts["host"], self.clientopts["port"], self.clientopts["sslctx"])
		else:
			self.log.msg("Proxy Client connecting TCP with opts "+repr(self.clientopts))
			d = c.connectTCP(self.clientopts["host"], self.clientopts["port"])
		# Always wait for the greeting before declaring success
		d.addCallback(self._getGreeting)
		d.addCallback(self._appendClient)
		return d

	def _appendClient(self, p):
		self.clients.append(p)
		self.log.msg("Proxy client added; %d clients in pool" % (len(self.clients),))
		return p

	def _getGreeting(self, p):
		d = p.getGreeting()
		d.addCallback(lambda _: p)
		return d

	def getClient(self):
		ready = None
		len_orig = len(self.clients)
		self.clients = filter(lambda p: not p.closed, self.clients)
		if len_orig - len(self.clients) > 0:
			self.log.msg("Removed %d closed proxy clients; %d clients in pool" % (len_orig - len(self.clients), len(self.clients)))
		for i, p in enumerate(self.clients):
			self.log.msg("Proxy client %d in state %s" % (i, p.state), logLevel=logging.DEBUG)
			if not ready and p.isReady() and not p.closed:
				ready = p
		if ready:
			return defer.succeed(ready)

		if len(self.clients) < self.max_clients:
			return self.newClient()

		self.log.msg("No proxy client available. Returning failure", logLevel=logging.ERROR)
		return defer.fail(ClientUnavailableError())

class EPPProxyServerFactory(protocol.ServerFactory):

	protocol = EPPProxyServer

	def __init__(self, clientopts, max_clients=1, max_retries=0, debug=False):
		self.client = EPPProxyClientPool(self, max_clients, clientopts)
		self.cache = {}
		self.max_retries = max_retries
		if debug:
			mylog.mask = logging.DEBUG

