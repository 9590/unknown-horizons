# -*- coding: utf-8 -*-
# ###################################################
# Copyright (C) 2012 The Unknown Horizons Team
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

__all__ = ['building', 'housing', 'nature', 'path', 'production', 'storages', 'settler', 'boatbuilder']

import logging

import horizons.main
from fife import fife

from horizons.util import ActionSetLoader
from horizons.i18n.objecttranslations import object_translations
from horizons.world.ingametype import IngameType

class BuildingClass(IngameType):
	"""Class that is used to create Building-Classes from the database.
	@param id: int - building id in the database.

	Note this creates classes, NOT instances. These are classes are created at the beginning of a session
	and are later used to create instances, when buildings are built.
	The __new__() function uses quite some python magic to construct the new class. Basically this is just cool
	and doesn't have a real benefit quite yet except for saving a little loading time.

	TUTORIAL:
	Check out the __new__() function if you feel your pretty good with python and are interested in how it all works,
	otherwise, continue to the __init__() function.
	"""
	log = logging.getLogger('world.building')

	def __new__(self, db, id,  yaml_data=[]):
		class_package =  yaml_data['baseclass'].split('.')[0]
		class_name = yaml_data['baseclass'].split('.')[1]

		__import__('horizons.world.building.'+class_package)
		@classmethod
		def load(cls, session, db, worldid):
			self = cls.__new__(cls)
			self.session = session
			super(cls, self).load(db, worldid)
			return self
		# Return the new type for this building, including it's attributes, like the previously defined load function.
		return type.__new__(self, 'Building[%s]' % str(id),
			(getattr(globals()[class_package], class_name),),
			{'load': load})

	def __init__(self, db, id, yaml_data=[]):
		"""
		Final loading for the building class. Load a lot of attributes for the building classes
		@param id: building id.
		@param db: DbReader
		"""
		super(BuildingClass, self).__init__(id, yaml_data)
		self.class_package = yaml_data['baseclass'].split('.')[0]
		# Override with translation here
		self._name = object_translations[yaml_data['yaml_file']]['name']
		self.button_name = yaml_data['button_name']
		self.settler_level = yaml_data['settler_level']
		try:
			self.tooltip_text = object_translations[yaml_data['yaml_file']]['tooltip_text']
		except KeyError: # not found => use value defined in yaml unless it is null
			tooltip_text = yaml_data['tooltip_text']
			if tooltip_text is not None:
				self.tooltip_text = tooltip_text
			else:
				self.tooltip_text = u''
		self.size = (int(yaml_data['size_x']), int(yaml_data['size_y']))
		self.inhabitants = int(yaml_data['inhabitants_start'])
		self.inhabitants_max = int(yaml_data['inhabitants_max'])
		self.costs = yaml_data['buildingcosts']
		self.running_costs = yaml_data['cost']
		self.running_costs_inactive = yaml_data['cost_inactive']
		self.has_running_costs = (self.running_costs != 0)
		# for mines: on which deposit is it buildable
		buildable_on_deposit_type = db("SELECT deposit FROM mine WHERE mine = ?", self.id)
		if buildable_on_deposit_type:
			self.buildable_on_deposit_type = buildable_on_deposit_type[0][0]

		self._loadObject()

		"""TUTORIAL: Now you know the basic attributes each building has. To check out further functions of single
		             buildings you should check out the separate classes in horizons/world/buildings/*.
					 Unit creation is very similar, you could check it out though and see which attributes a unit
					 always has.
					 As most of the buildings are derived from the production/provider/consumer classes, which are
					 derived from the storageholder, I suggest you start digging deeper there.
					 horizons/world/storageholder.py is the next place to go.
					 """


	def __str__(self):
		return "Building[" + str(self.id) + "](" + self._name + ")"

	def _loadObject(cls):
		"""Loads building from the db.
		"""
		cls.log.debug("Loading building %s", cls.id)
		try:
			cls._object = horizons.main.fife.engine.getModel().createObject(str(cls.id), 'building')
		except RuntimeError:
			cls.log.debug("Already loaded building %s", cls.id)
			cls._object = horizons.main.fife.engine.getModel().getObject(str(cls.id), 'building')
			return
		action_sets = cls.action_sets.iterkeys()
		all_action_sets = ActionSetLoader.get_sets()
		for action_set_id in action_sets:
			for action_id in all_action_sets[action_set_id].iterkeys():
				action = cls._object.createAction(action_id+"_"+str(action_set_id))
				fife.ActionVisual.create(action)
				for rotation in all_action_sets[action_set_id][action_id].iterkeys():
					#print "rotation:", rotation
					if rotation == 45:
						command = 'left-32,bottom+' + str(cls.size[0] * 16)
					elif rotation == 135:
						command = 'left-' + str(cls.size[1] * 32) + ',bottom+16'
					elif rotation == 225:
						command = 'left-' + str((cls.size[0] + cls.size[1] - 1) * 32) + ',bottom+' + str(cls.size[1] * 16)
					elif rotation == 315:
						command = 'left-' + str(cls.size[0] * 32) + ',bottom+' + str((cls.size[0] + cls.size[1] - 1) * 16)
					else:
						assert False, "Bad rotation for action_set %(id)s: %(rotation)s for action: %(action_id)s" % \
							   { 'id':action_set_id, 'rotation': rotation, 'action_id': action_id }
					anim = horizons.main.fife.animationloader.loadResource(str(action_set_id)+"+"+str(action_id)+"+"+str(rotation) + ':shift:' + command)
					action.get2dGfxVisual().addAnimation(int(rotation), anim)
					action.setDuration(anim.getDuration())
