#!/usr/bin/env python

# ###################################################
# Copyright (C) 2009 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

"""This is the Unknown Horizons launcher, it looks for fife and tries to start the game. If you want to dig
into the game, continue to horizons/main.py. Read all docstrings and get familiar with the functions and
attributes. I will mark all tutorial instructions with 'TUTORIAL:'. Have fun :-)"""

import sys
import os
import os.path
import gettext
import time
import logging
import logging.config
import logging.handlers
import optparse
import traceback

def log():
	"""Returns Logger"""
	return logging.getLogger("run_uh")

def find_uh_position():
	"""Returns path, where uh is located"""
	first_guess = os.path.split( os.path.realpath( sys.argv[0]) )[0]
	if os.path.exists('%s/content' % first_guess):
		return first_guess
	else:
		positions = ['/usr/share/games',
			     '/usr/share',
			     '/usr/local/share/games',
			     '/usr/local/share',
			     ]

		for i in positions:
			if os.path.exists('%s/unknown-horizons' % i):
				return '%s/unknown-horizons' % i

def get_option_parser():
	"""Returns inited OptionParser object"""
	p = optparse.OptionParser()
	p.add_option("-d", "--debug", dest="debug", action="store_true", default=False, \
							 help=_("Enable debug output"))
	p.add_option("--fife-path", dest="fife_path", metavar="<path>", \
							 help=_("Specify the path to FIFE root directory."))

	start_uh_group = optparse.OptionGroup(p, _("Starting unknown horizons"))
	start_uh_group.add_option("--start-map", dest="start_map", metavar="<map>", \
														help=_("Starts <map>. <map> is the mapname (filename without extension)"))
	start_uh_group.add_option("--start-dev-map", dest="start_dev_map", action="store_true", \
			default=False, help=_("Starts the development map without displaying the main menu."))
	start_uh_group.add_option("--load-map", dest="load_map", metavar="<save>", \
														help=_("Loads a saved game. <save> is the savegamename."))
	start_uh_group.add_option("--load-last-quicksave", dest="load_quicksave", action="store_true", \
														help=_("Loads the last quicksave."))
	p.add_option_group(start_uh_group)

	dev_group = optparse.OptionGroup(p, _("Development options"))
	dev_group.add_option("--debug-log-only", dest="debug_log_only", action="store_true", \
	                     default=False, help=_("Write debug output only to logfile, not to console"))
	dev_group.add_option("--debug-module", action="append", dest="debug_module", \
											 metavar="<module>", default=[], \
											 help=_("Enable logging for a certain logging module."))
	dev_group.add_option("--fife-in-library-path", dest="fife_in_library_path", \
											 action="store_true", default=False, help=_("For internal use only."))
	dev_group.add_option("--enable-unstable-features", dest="unstable_features", \
											 action="store_true", default=False, help=_("Enables unstable features"))
	dev_group.add_option("--profile", dest="profile", action="store_true", default=False, \
											 help=_("Enable profiling"))
	p.add_option_group(dev_group)

	return p

def create_user_dirs():
	"""Creates the userdir and subdirs. Includes from horizons."""
	from horizons.constants import PATHS
	for directory in [PATHS.USER_DIR, PATHS.LOG_DIR]:
		if not os.path.isdir(directory):
			os.makedirs(directory)

def excepthook_creator(outfilename):
	"""Returns an excepthook function to replace sys.excepthook.
	The returned function does the same as the default, except it also prints the traceback
	to a file.
	@param outfilename: a filename to append traceback to"""
	def excepthook(exception_type, value, tb):
		f = open(outfilename, 'a')
		traceback.print_exception(exception_type, value, tb, file=f)
		traceback.print_exception(exception_type, value, tb)
		print
		print _('Unknown Horizons crashed.')
		print
		print _('We are very sorry for this, and want to fix this error.')
		print _('In order to do this, we need the information from the logfile:')
		print outfilename
		print _('Please give it to us via IRC or our forum, for both see unknown-horizons.org .')
	return excepthook

def main():
	#chdir to Unknown Horizons root
	os.chdir( find_uh_position() )
	logging.config.fileConfig('content/logging.conf')
	gettext.install("unknownhorizons", "po", unicode=1)

	create_user_dirs()

	parser = get_option_parser()
	(options, args) = parser.parse_args()

	# apply options
	if options.debug:
		logging.getLogger().setLevel(logging.DEBUG)
	for module in options.debug_module:
		if not module in logging.Logger.manager.loggerDict:
			print 'No such logger:', module
			sys.exit(1)
		logging.getLogger(module).setLevel(logging.DEBUG)
	if options.debug or len(options.debug_module) > 0 or options.debug_log_only:
		# also log to file
		# init a logfile handler with a dynamic filename
		from horizons.constants import PATHS
		logfilename = PATHS.LOG_DIR + "/unknown-horizons-%s.log" % \
		            time.strftime("%y-%m-%d_%H-%M-%S")
		print 'Logging to %s' % logfilename
		file_handler = logging.FileHandler(logfilename, 'w')
		logging.getLogger().addHandler(file_handler)
		sys.excepthook = excepthook_creator(logfilename)
	if not options.debug_log_only:
		# add a handler to stderr
		logging.getLogger().addHandler( logging.StreamHandler(sys.stderr) )

	# NOTE: this might cause a program restart
	init_environment()

	#start unknownhorizons
	import horizons.main
	if not options.profile:
		# start normal
		horizons.main.start(options)
	else:
		# start with profiling
		import profile
		import tempfile
		outfilename = tempfile.mkstemp(text = True)[1]
		log().warning('Starting profile mode. Writing output to: %s', outfilename)
		profile.runctx('horizons.main.start(options)', globals(), locals(), \
									 outfilename)
		log().warning('Program ended. Profiling output: %s', outfilename)

	print _('Thank you for using Unknown Horizons!')


"""
Functions controlling the program environment.
NOTE: these are supposed to be in an extra file, but are placed here for simplifying
			distribution
"""
def init_environment():
	"""Sets up everything. Use in any program that requires access to fife and uh modules.
	It will parse sys.args, so this var has to contain only valid uh options."""
	create_user_dirs()

	gettext.install("unknownhorizons", "po", unicode=1)

	(options, args) = get_option_parser().parse_args()

	#find fife and setup search paths, if it can't be imported yet
	try:
		import fife
	except ImportError, e:
		if options.fife_in_library_path:
			# fife should already be in LD_LIBRARY_PATH
			print 'Failed to load fife:', e
			exit(1)
		log().debug('Searching for FIFE')
		find_FIFE(options.fife_path) # this restarts or terminates the program
		assert False

	#for some external libraries distributed with unknownhorizons
	sys.path.append('horizons/ext')

	args_to_discard_now = ['--fife-in-library-path', '--fife-path']
	for arg in args_to_discard_now:
		if arg in sys.argv:
			sys.argv.remove(arg)

def get_fife_path(fife_custom_path=None):
	"""Returns absolute path to fife engine. Calls sys.exit() if it can't be found."""
	# assemble a list of paths where fife could be located at
	_paths = []
	# check if there is a config file (has to be called config.py)
	try:
		import config
		_paths.append(config.fife_path)
		if not check_path_for_fife(config.fife_path):
			print 'Invalid fife_path in config.py: %s' % config.fife_path
	except (ImportError, AttributeError):
		# no config, check for commandline arg
		if fife_custom_path is not None:
			_paths.append(fife_custom_path)
			if not check_path_for_fife(fife_custom_path):
				print 'Specified invalid fife path: %s' %  fife_custom_path

		else:
			# try frequently used paths
			_paths += [ a + '/' + b + '/' + c for \
									a in ('.', '..', '../..') for \
									b in ('.', 'fife', 'FIFE', 'Fife') for \
									c in ('.', 'trunk') ]

	fife_path = None
	for p in _paths:
		if p not in sys.path: # skip dirs where import would have found fife
			p = os.path.abspath(p)
			log().debug("Searching for FIFE in %s", p)
			if check_path_for_fife(p):
				fife_path = p

				log().debug("Found FIFE in %s", fife_path)

				#add python paths (<fife>/engine/extensions <fife>/engine/swigwrappers/python)
				for pe in [ fife_path + os.path.sep + a for \
							a in ('engine/extensions', 'engine/swigwrappers/python') ]:
					if os.path.exists(pe):
						sys.path.append(pe)
				os.environ['PYTHONPATH'] = os.path.pathsep.join(\
					os.environ.get('PYTHONPATH', '').split(os.path.pathsep) + \
					[ fife_path + os.path.sep + a for a in \
						('engine/extensions', 'engine/swigwrappers/python') ])

				#add windows paths (<fife>/.)
				os.environ['PATH'] = os.path.pathsep.join( \
					os.environ.get('PATH', '').split(os.path.pathsep) + [ fife_path ] )
				os.path.defpath += os.path.pathsep + fife_path
				break
	else:
		print _('FIFE was not found.')
		sys.exit(1)
	return fife_path

def check_path_for_fife(path):
	absolute_path = os.path.abspath(path)
	for pe in [ '%s/%s' % (absolute_path, a) for a in ('.', 'engine', 'engine/extensions',  \
																										 'engine/swigwrappers/python') ]:
		if not os.path.exists(pe):
			return False
	return True

def find_FIFE(fife_custom_path=None):
	"""Inserts path to fife engine to $LD_LIBRARY_PATH (environment variable).
	If it's already there, the function will return, else
	it will restart uh with correct $LD_LIBRARY_PATH. """
	fife_path = get_fife_path(fife_custom_path) # terminates program if fife can't be found

	os.environ['LD_LIBRARY_PATH'] = os.path.pathsep.join( \
		[ os.path.abspath(fife_path + '/' + a) for  \
			a in ('ext/minizip', 'ext/install/lib') ] + \
		  (os.environ['LD_LIBRARY_PATH'].split(os.path.pathsep) if \
			 os.environ.has_key('LD_LIBRARY_PATH') else []))

	log().debug("Restarting with proper LD_LIBRARY_PATH...")
	log().debug("LD_LIBRARY_PATH: %s", os.environ['LD_LIBRARY_PATH'])
	log().debug("PATH: %s", os.environ['PATH'])
	log().debug("PYTHONPATH %s", os.environ['PYTHONPATH'])

	# assemble args (python run_uh.py ..)
	args = [sys.executable] + sys.argv + [ "--fife-in-library-path"]
	log().debug("Restarting with args %s", args)
	os.execvp(args[0], args)


if __name__ == '__main__':
	main()
