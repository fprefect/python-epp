
import os
import ConfigParser
from twisted.application import service, internet
from twisted.python import log
from epp import server
from OpenSSL import SSL

class ServerContextFactory():
	def __init__(self, certificate_file, privatekey_file, cafile=False):
		if not os.path.exists(certificate_file): raise IOError("File '%s' does not exist" % certificate_file)
		if not os.path.exists(privatekey_file): raise IOError("File '%s' does not exist" % privatekey_file)
		if cafile and not os.path.exists(cafile): raise IOError("File '%s' does not exist" % cafile)
		self.cf = certificate_file
		self.kf = privatekey_file
		self.ca = cafile
	def getContext(self):
		ctx = SSL.Context(SSL.SSLv23_METHOD)
		ctx.use_certificate_file(self.cf)
		ctx.use_privatekey_file(self.kf)
		if self.ca: ctx.load_verify_locations(self.ca)
		return ctx

def GetConfigFilename():
	# First check environment
	filename = os.environ.get('EPP_RPROXY_CONFIG')
	if filename:
		if os.path.exists(filename):
				return filename
		raise IOError("File '%s' does not exist" % filename)

	# Next, standard loc
	filename = '/etc/epp/epp-rproxy.conf'
	if os.path.exists(filename):
		return filename
	raise IOError("File '%s' does not exist" % filename)


config = ConfigParser.ConfigParser({
	'timeout': '10',
	'keepalive_interval': '0',
	'listen_host': '127.0.0.1',
})

config.read(GetConfigFilename())

application = service.Application('EPP Reverse Proxy Server')
serviceCollection = service.IServiceCollection(application)


print "ServerOptions:"+repr(application)


#observer = log.PythonLoggingObserver(filename=filename)
#application.setComponent(ILogObserver, observer.emit)

for section in config.sections():
	log.msg("Loading config section: %s" % section)

	sslctx = None
	if config.get(section,'proto') == 'ssl':
		sslctx = ServerContextFactory(config.get(section, 'crtfile'), config.get(section, 'keyfile'), config.get(section,'cafile'))

	clientopts = {
		"host": config.get(section,'host'),
		"port": config.getint(section, 'port'),
		"timeout": config.getint(section,'timeout'),
		"sslctx": sslctx,
		"keepalive_interval": config.getint(section,'keepalive_interval'),
	}

	s = internet.TCPServer(config.getint(section, 'listen_port'), 
								server.EPPProxyServerFactory(clientopts, 
															 max_clients=config.getint(section,'max_clients'), 
															 max_retries=config.getint(section,'max_retries')), 
								interface=config.get(section, 'listen_host'))

	s.setServiceParent(serviceCollection)

