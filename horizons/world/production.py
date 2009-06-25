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

import horizons.main

from provider import Provider
from consumer import Consumer
from building.building import Building
from horizons.gui.tabs import TabWidget, ProductionOverviewTab, InventoryTab


class ProductionLine(object):
	"""Data structur for handling production lines of Producers. A production line
	is a way of producing something (contains needed and produced resources for this line,
	as well as the time, that it takes to complete the product."""
	def __init__(self, ident):
		self.id = ident
		self.time = horizons.main.db("SELECT time FROM data.production_line WHERE rowid = ?", self.id)[0][0]
		# here we store all resource information.
		# needed resources have a negative amount, produced ones are positive.
		self.production = {}
		for res, amount in horizons.main.db("SELECT resource, amount FROM data.production WHERE production_line = ?", self.id):
			self.production[res] = amount


class PrimaryProducer(Provider):
	"""Class used for primary production classes. These types do not need other ressources to
	produce something. A tree is a primary producer for example, it 'just grows' and produces
	wood out of nowhere.

	TUTORIAL:
	Check out the __init() function now."""
	def __init__(self, **kwargs):
		super(PrimaryProducer, self).__init__(**kwargs)
		self._init()

	def _init(self):
		self.production = {}
		self.active_production_line = None
		self.active = False
		self.inventory.limit = 4
		# Stores the current production's progress
		self.progress = 0

		# The PrimaryProducer uses a simular way of ProductionLines as the Consumer, the only
		# difference is, that is uses a seperate class for ProductionLines as some more details
		# need to be stored.
		# TUTORIAL:
		# Check that class out now and then come back here.
		for (ident,) in horizons.main.db("SELECT rowid FROM data.production_line where %(type)s = ?" % {'type' : 'building' if self.object_type == 0 else 'unit'}, self.id):
			self.production[ident] = ProductionLine(ident)

		self.__used_resources = {}
		self.toggle_active() # start production
		if isinstance(self, Building):
			self.toggle_costs()  # needed to get toggle to the right position

		"""TUTORIAL:
		You can check out the further functions in this class if you like, they are rather messy
		and not too import for now, you can look at them if you need them. Continue to the
		SecondaryProducer below now.
		"""

	def toggle_active(self):
		"""Toggles the production of this instance active/inactive."""
		if self.active:
			self.active_production_line = None
			if self.hasChangeListener(self.check_production_startable):
				self.removeChangeListener(self.check_production_startable)
			horizons.main.session.scheduler.rem_call(self, self.production_step)
			if isinstance(self, Building):
				self.toggle_costs()
		else:
			if self.active_production_line is None and len(self.production) > 0:
				# more than one production line => select first one
				self.active_production_line = min(self.production.keys())
			if self.active_production_line is not None:
				self.addChangeListener(self.check_production_startable)
				self.check_production_startable()
			if isinstance(self, Building):
				self.toggle_costs()
		self.active = (not self.active)
		self._changed()

	def save(self, db):
		super(PrimaryProducer, self).save(db)
		db("INSERT INTO production(rowid, active_production_line) VALUES(?, ?)", \
		   self.getId(), self.active_production_line)

	def load(self, db, worldid):
		super(PrimaryProducer, self).load(db, worldid)
		active_production_line = db("SELECT active_production_line FROM production WHERE rowid = ?", worldid)
		assert(0 <= len(active_production_line) <= 1)
		if len(active_production_line) == 0:
			self.active_production_line = None
		else:
			self.active_production_line = active_production_line[0][0]
		self._init()

	def check_production_startable(self):
		"""Do the production of resources according to the selected production line.
		Checks if resources, that are needed for production, are in inventory first."""
		if self.active_production_line is None:
			# no production line selected, so we don't know what to produce
			return

		# check if we have space for the items we want to produce
		if not self._can_produce():
			return

		# TODO: document useable and used resources (what are they, when do we need them)
		usable_resources = {}
		if min(self.production[self.active_production_line].production.values()) < 0:
			for res, amount in self.production[self.active_production_line].production.items():
				#we have something to work with, if the res is needed, we have something in the inv and we dont already have used everything we need from that resource
				if amount < 0 and self.inventory[res] > 0 and self.__used_resources.get(res, 0) < -amount:
					# Make sure there are enough resources in the inventory
					if self.inventory[res] > -amount - self.__used_resources.get(res, 0):
						usable_resources[res] = -amount - self.__used_resources.get(res, 0)
					else:
						usable_resources[res] = self.inventory[res]
			if len(usable_resources) == 0:
				return
			time = int(round(self.production[self.active_production_line].time *
							 sum(self.__used_resources.values()) /
							 -sum(p for p in self.production[self.active_production_line].production.values() if p < 0)))
		else:
			time = 0
		for res, amount in usable_resources.items():
			if res in self.__used_resources:
				self.__used_resources[res] += amount
			else:
				self.__used_resources[res] = amount
			self._set_progress()

		for res, amount in usable_resources.items():
			# remove the needed resources from the inventory
			remnant = self.inventory.alter(res, -amount)
			assert(remnant == 0)

		# Make sure we bail out if we have not yet collected everything
		for res, amount in self.production[self.active_production_line].production.items():
			if amount < 0 and (
				(res in self.__used_resources and self.__used_resources[res] < -amount) or
				res not in self.__used_resources):
				return
		self.removeChangeListener(self.check_production_startable)

		# TODO: make following lines readable and document them.
		horizons.main.session.scheduler.add_new_object(self.production_step, self, 16 *
			(self.production[self.active_production_line].time if min(self.production[self.active_production_line].production.values()) >= 0
			else (int(round(self.production[self.active_production_line].time * sum(self.__used_resources.values()) / -sum(p for p in self.production[self.active_production_line].production.values() if p < 0))
					  ) - time)))
		# change animation to working.
		# this starts e.g. the growing of trees.
		if "work" in horizons.main.action_sets[self._action_set_id].keys():
			self.act("work", self._instance.getFacingLocation(), True)
		else:
			self.act("idle", self._instance.getFacingLocation(), True)

	def production_step(self):
		if sum(self.__used_resources.values()) >= -sum(p for p in self.production[self.active_production_line].production.values() if p < 0):
			for res, amount in self.production[self.active_production_line].production.items():
				if amount > 0:
					self.inventory.alter(res, amount)
			self.__used_resources = {}
		if "idle_full" in horizons.main.action_sets[self._action_set_id].keys():
			self.act("idle_full", self._instance.getFacingLocation(), True)
		else:
			self.act("idle", self._instance.getFacingLocation(), True)
		self.addChangeListener(self.check_production_startable)
		self.check_production_startable()


	def _set_progress(self):
		"""Sets the current progress correctly.
		This method can be overriden in case subclasses calculate differently.
		"""
		self.progress = int(float(len(self.__used_resources.values()))/
			float(
				-sum(product for product in
					self.production[self.active_production_line].production.values() if product < 0
				)
			)*100)
		#print self.progress


	def _can_produce(self):
		"""This function checks whether the producer is ready to start production.
		Can be overriden to implement buildingspecific behaviour.
		"""
		for res, amount in self.production[self.active_production_line].production.items():
			if amount > 0 and self.inventory[res] + amount > self.inventory.get_limit(res):
				return False
		return True

class SecondaryProducer(Consumer, PrimaryProducer):
	"""Represents a producer, that consumes ressources for production of other ressources
	(e.g. blacksmith).

	TUTORIAL:
	As you may notice through the detailed distinction of Consumer and Producer classes, it's now
	very simple to create new classes with the wanted behavior. You will notice that we love this
	way of doing things and tend to abstract as much as possible.

	By now you should have a fair overview of how Unknown Horizons works. The tutorial ends here. From now
	you might want to take a look into the horizons/gui and horizons/util folders to checkout the workings
	of the gui and some extra stuff we use. Since you came all the way here, you are now ready to
	get your hands dirty and start working. So check out the bugtracker at www.unknown-horizons.org/trac/
	and see if there's a nice ticket for you :) For further questions just visit us on irc:
	#unknown-horizons @ irc.freenode.net. We'll be happy to answer any questions.

	Have fun with Unknown Horizons!
	"""

	def show_menu(self):
		horizons.main.session.ingame_gui.show_menu(TabWidget(tabs= [ProductionOverviewTab(self), InventoryTab(self)]))


