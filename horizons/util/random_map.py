# ###################################################
# Copyright (C) 2011 The Unknown Horizons Team
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
import random
import tempfile
import sys
import shutil
import re
import string
import copy

from horizons.util import Circle, Rect, Point, DbReader
from horizons.constants import GROUND, PATHS
from horizons.ext.enum import Enum

# this is how a random island id looks like (used for creation)
_random_island_id_template = "random:${creation_method}:${width}:${height}:${seed}"

# you can check for a random island id with this:
_random_island_id_regexp = r"random:([0-9]+):([0-9]+):([0-9]+):([\-]?[0-9]+)"


def is_random_island_id_string(id_string):
	"""Returns whether id_string is an instance of a random island id string"""
	return bool(re.match(_random_island_id_regexp, id_string))

def create_random_island(id_string):
	"""Creates a random island as sqlite db.
	It is rather primitive; it places shapes on the dict.
	The coordinates of tiles will be 0 <= x < width and 0 <= y < height
	@param id_string: random island id string
	@return: sqlite db reader containing island
	"""
	# NOTE: the tilesystem will be redone soon, so constants indicating grounds are temporary
	# here and will have to be changed anyways.
	match_obj = re.match(_random_island_id_regexp, id_string)
	assert match_obj
	creation_method, width, height, seed = [ long(i) for i in match_obj.groups() ]

	rand = random.Random(seed)

	map_set = set()

	# creation_method 0 - standard small island for the 3x3 grid
	# creation_method 1 - large island
	# creation_method 2 - a number of randomly sized and placed islands

	# place this number of shapes
	for i in xrange(15 + width * height / 45):
		# place shape determined by shape_id on (x, y)
		add = True
		rect_chance = 6
		if creation_method == 0:
			shape_id = rand.randint(3, 5)
		elif creation_method == 1:
			shape_id = rand.randint(5, 8)
		elif creation_method == 2:
			shape_id = rand.randint(2, 8)
			rect_chance = 29
			if rand.randint(0, 4) == 0:
				rect_chance = 13
				add = False

		shape = None
		if rand.randint(1, rect_chance) == 1:
			# use a rect
			if add:
				x = rand.randint(8, width - 7)
				y = rand.randint(8, height - 7)
				if creation_method == 0:
					shape = Rect.init_from_topleft_and_size(x - 3, y - 3, 5, 5)
				elif creation_method == 1:
					shape = Rect.init_from_topleft_and_size(x - 5, y - 5, 8, 8)
				elif creation_method == 2:
					shape = Rect.init_from_topleft_and_size(x - 5, y - 5, rand.randint(2, 8), rand.randint(2, 8))
			else:
				x = rand.randint(0, width)
				y = rand.randint(0, height)
				shape = Rect.init_from_topleft_and_size(x - 5, y - 5, rand.randint(2, 8), rand.randint(2, 8))
		else:
			# use a circle, where radius is determined by shape_id
			radius = shape_id
			if not add and rand.randint(0, 6) < 5:
				x = rand.randint(-radius * 3 / 2, width + radius * 3 / 2)
				y = rand.randint(-radius * 3 / 2, height + radius * 3 / 2)
				shape = Circle(Point(x, y), shape_id)
			elif width - radius - 4 >= radius + 3 and height - radius - 4 >= radius + 3:
				x = rand.randint(radius + 3, width - radius - 4)
				y = rand.randint(radius + 3, height - radius - 4)
				shape = Circle(Point(x, y), shape_id)

		if shape:
			for shape_coord in shape.tuple_iter():
				if add:
					map_set.add(shape_coord)
				elif shape_coord in map_set:
					map_set.discard(shape_coord)

	# write values to db
	map_db = DbReader(":memory:")
	map_db("CREATE TABLE ground(x INTEGER NOT NULL, y INTEGER NOT NULL, ground_id INTEGER NOT NULL, action_id TEXT NOT NULL, rotation INTEGER NOT NULL)")
	map_db("CREATE TABLE island_properties(name TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)")
	map_db("BEGIN TRANSACTION")

	# add grass tiles
	for x, y in map_set:
		map_db("INSERT INTO ground VALUES(?, ?, ?, ?, ?)", x, y, *GROUND.DEFAULT_LAND)

	def fill_tiny_spaces(tile):
		"""Fills 1 tile gulfs and straits with the specified tile
		@param tile: ground tile to fill with
		"""

		all_neighbours = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
		neighbours = [(-1, 0), (0, -1), (0, 1), (1, 0)]
		corners = [(-1, -1), (-1, 1)]
		knight_moves = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
		bad_configs = set([0, 1 << 0, 1 << 1, 1 << 2, 1 << 3, (1 << 0) | (1 << 3), (1 << 1) | (1 << 2)])

		edge_set = copy.copy(map_set)
		reduce_edge_set = True

		while True:
			to_fill = set()
			to_ignore = set()
			for x, y in edge_set:
				# ignore the tiles with no empty neighbours
				if reduce_edge_set:
					is_edge = False
					for x_offset, y_offset in all_neighbours:
						if (x + x_offset, y + y_offset) not in map_set:
							is_edge = True
							break
					if not is_edge:
						to_ignore.add((x, y))
						continue

				for x_offset, y_offset in neighbours:
					x2 = x + x_offset
					y2 = y + y_offset
					if (x2, y2) in map_set:
						continue
					# (x2, y2) is now a point just off the island

					neighbours_dirs = 0
					for i in xrange(len(neighbours)):
						x3 = x2 + neighbours[i][0]
						y3 = y2 + neighbours[i][1]
						if (x3, y3) not in map_set:
							neighbours_dirs |= (1 << i)
					if neighbours_dirs in bad_configs:
						# part of a straight 1 tile gulf
						to_fill.add((x2, y2))
					else:
						for x_offset, y_offset in corners:
							x3 = x2 + x_offset
							y3 = y2 + y_offset
							x4 = x2 - x_offset
							y4 = y2 - y_offset
							if (x3, y3) in map_set and (x4, y4) in map_set:
								# part of a diagonal 1 tile gulf
								to_fill.add((x2, y2))
								break

				# block 1 tile straits
				for x_offset, y_offset in knight_moves:
					x2 = x + x_offset
					y2 = y + y_offset
					if (x2, y2) not in map_set:
						continue
					if abs(x_offset) == 1:
						y2 = y + y_offset / 2
						if (x2, y2) in map_set or (x, y2) in map_set:
							continue
					else:
						x2 = x + x_offset / 2
						if (x2, y2) in map_set or (x2, y) in map_set:
							continue
					to_fill.add((x2, y2))

				# block diagonal 1 tile straits
				for x_offset, y_offset in corners:
					x2 = x + x_offset
					y2 = y + y_offset
					x3 = x + 2 * x_offset
					y3 = y + 2 * y_offset
					if (x2, y2) not in map_set and (x3, y3) in map_set:
						to_fill.add((x2, y2))
					elif (x2, y2) in map_set and (x2, y) not in map_set and (x, y2) not in map_set:
						to_fill.add((x2, y))

			if to_fill:
				for x, y in to_fill:
					map_set.add((x, y))
					map_db("INSERT INTO ground VALUES(?, ?, ?, ?, ?)", x, y, *tile)

				old_size = len(edge_set)
				edge_set = edge_set.difference(to_ignore).union(to_fill)
				reduce_edge_set = old_size - len(edge_set) > 50
			else:
				break

	# possible movement directions
	all_moves = {
		'sw' : (-1, -1),
		'w'  : (-1, 0),
		'nw' : (-1, 1),
		's'  : (0, -1),
		'n'  : (0, 1),
		'se' : (1, -1),
		'e'  : (1, 0),
		'ne' : (1, 1)
		}

	def get_island_outline():
		"""
		@return: the points just off the island as a dict
		"""
		result = set()
		for x, y in map_set:
			for offset_x, offset_y in all_moves.itervalues():
				coords = (x + offset_x, y + offset_y)
				if coords not in map_set:
					result.add(coords)
		return result

	# add grass to sand tiles
	fill_tiny_spaces(GROUND.DEFAULT_LAND)
	outline = get_island_outline()
	for x, y in outline:
		filled = []
		for dir in sorted(all_moves):
			coords = (x + all_moves[dir][1], y + all_moves[dir][0])
			if coords in map_set:
				filled.append(dir)

		tile = None
		# straight coast or 1 tile U-shaped gulfs
		if filled == ['s', 'se', 'sw'] or filled == ['s']:
			tile = GROUND.SAND_NORTH
		elif filled == ['e', 'ne', 'se'] or filled == ['e']:
			tile = GROUND.SAND_WEST
		elif filled == ['n', 'ne', 'nw'] or filled == ['n']:
			tile = GROUND.SAND_SOUTH
		elif filled == ['nw', 'sw', 'w'] or filled == ['w']:
			tile = GROUND.SAND_EAST
		# slight turn (looks best with straight coast)
		elif filled == ['e', 'se'] or filled == ['e', 'ne']:
			tile = GROUND.SAND_WEST
		elif filled == ['n', 'ne'] or filled == ['n', 'nw']:
			tile = GROUND.SAND_SOUTH
		elif filled == ['nw', 'w'] or filled == ['sw', 'w']:
			tile = GROUND.SAND_EAST
		elif filled == ['s', 'sw'] or filled == ['s', 'se']:
			tile = GROUND.SAND_NORTH
		# sandy corner
		elif filled == ['se']:
			tile = GROUND.SAND_NORTHWEST1
		elif filled == ['ne']:
			tile = GROUND.SAND_SOUTHWEST1
		elif filled == ['nw']:
			tile = GROUND.SAND_SOUTHEAST1
		elif filled == ['sw']:
			tile = GROUND.SAND_NORTHEAST1
		# grassy corner
		elif 3 <= len(filled) <= 5:
			coast_set = set(filled)
			if 'e' in coast_set and 'se' in coast_set and 's' in coast_set:
				tile = GROUND.SAND_NORTHEAST3
			elif 's' in coast_set and 'sw' in coast_set and 'w' in coast_set:
				tile = GROUND.SAND_NORTHWEST3
			elif 'w' in coast_set and 'nw' in coast_set and 'n' in coast_set:
				tile = GROUND.SAND_SOUTHWEST3
			elif 'n' in coast_set and 'ne' in coast_set and 'e' in coast_set:
				tile = GROUND.SAND_SOUTHEAST3

		assert tile
		map_db("INSERT INTO ground VALUES(?, ?, ?, ?, ?)", x, y, *tile)
	map_set = map_set.union(outline)

	# add sand to shallow water tiles
	fill_tiny_spaces(GROUND.SAND)
	outline = get_island_outline()
	for x, y in outline:
		filled = []
		for dir in sorted(all_moves):
			coords = (x + all_moves[dir][1], y + all_moves[dir][0])
			if coords in map_set:
				filled.append(dir)

		tile = None
		# straight coast or 1 tile U-shaped gulfs
		if filled == ['s', 'se', 'sw'] or filled == ['s']:
			tile = GROUND.COAST_NORTH
		elif filled == ['e', 'ne', 'se'] or filled == ['e']:
			tile = GROUND.COAST_WEST
		elif filled == ['n', 'ne', 'nw'] or filled == ['n']:
			tile = GROUND.COAST_SOUTH
		elif filled == ['nw', 'sw', 'w'] or filled == ['w']:
			tile = GROUND.COAST_EAST
		# slight turn (looks best with straight coast)
		elif filled == ['e', 'se'] or filled == ['e', 'ne']:
			tile = GROUND.COAST_WEST
		elif filled == ['n', 'ne'] or filled == ['n', 'nw']:
			tile = GROUND.COAST_SOUTH
		elif filled == ['nw', 'w'] or filled == ['sw', 'w']:
			tile = GROUND.COAST_EAST
		elif filled == ['s', 'sw'] or filled == ['s', 'se']:
			tile = GROUND.COAST_NORTH
		# mostly wet corner
		elif filled == ['se']:
			tile = GROUND.COAST_NORTHWEST1
		elif filled == ['ne']:
			tile = GROUND.COAST_SOUTHWEST1
		elif filled == ['nw']:
			tile = GROUND.COAST_SOUTHEAST1
		elif filled == ['sw']:
			tile = GROUND.COAST_NORTHEAST1
		# mostly dry corner
		elif 3 <= len(filled) <= 5:
			coast_set = set(filled)
			if 'e' in coast_set and 'se' in coast_set and 's' in coast_set:
				tile = GROUND.COAST_NORTHEAST3
			elif 's' in coast_set and 'sw' in coast_set and 'w' in coast_set:
				tile = GROUND.COAST_NORTHWEST3
			elif 'w' in coast_set and 'nw' in coast_set and 'n' in coast_set:
				tile = GROUND.COAST_SOUTHWEST3
			elif 'n' in coast_set and 'ne' in coast_set and 'e' in coast_set:
				tile = GROUND.COAST_SOUTHEAST3

		assert tile
		map_db("INSERT INTO ground VALUES(?, ?, ?, ?, ?)", x, y, *tile)
	map_set = map_set.union(outline)

	# add shallow water to deep water tiles
	fill_tiny_spaces(GROUND.SHALLOW_WATER)
	outline = get_island_outline()
	for x, y in outline:
		filled = []
		for dir in sorted(all_moves):
			coords = (x + all_moves[dir][1], y + all_moves[dir][0])
			if coords in map_set:
				filled.append(dir)

		tile = None
		# straight coast or 1 tile U-shaped gulfs
		if filled == ['s', 'se', 'sw'] or filled == ['s']:
			tile = GROUND.DEEP_WATER_NORTH
		elif filled == ['e', 'ne', 'se'] or filled == ['e']:
			tile = GROUND.DEEP_WATER_WEST
		elif filled == ['n', 'ne', 'nw'] or filled == ['n']:
			tile = GROUND.DEEP_WATER_SOUTH
		elif filled == ['nw', 'sw', 'w'] or filled == ['w']:
			tile = GROUND.DEEP_WATER_EAST
		# slight turn (looks best with straight coast)
		elif filled == ['e', 'se'] or filled == ['e', 'ne']:
			tile = GROUND.DEEP_WATER_WEST
		elif filled == ['n', 'ne'] or filled == ['n', 'nw']:
			tile = GROUND.DEEP_WATER_SOUTH
		elif filled == ['nw', 'w'] or filled == ['sw', 'w']:
			tile = GROUND.DEEP_WATER_EAST
		elif filled == ['s', 'sw'] or filled == ['s', 'se']:
			tile = GROUND.DEEP_WATER_NORTH
		# mostly deep corner
		elif filled == ['se']:
			tile = GROUND.DEEP_WATER_NORTHWEST1
		elif filled == ['ne']:
			tile = GROUND.DEEP_WATER_SOUTHWEST1
		elif filled == ['nw']:
			tile = GROUND.DEEP_WATER_SOUTHEAST1
		elif filled == ['sw']:
			tile = GROUND.DEEP_WATER_NORTHEAST1
		# mostly shallow corner
		elif 3 <= len(filled) <= 5:
			coast_set = set(filled)
			if 'e' in coast_set and 'se' in coast_set and 's' in coast_set:
				tile = GROUND.DEEP_WATER_NORTHEAST3
			elif 's' in coast_set and 'sw' in coast_set and 'w' in coast_set:
				tile = GROUND.DEEP_WATER_NORTHWEST3
			elif 'w' in coast_set and 'nw' in coast_set and 'n' in coast_set:
				tile = GROUND.DEEP_WATER_SOUTHWEST3
			elif 'n' in coast_set and 'ne' in coast_set and 'e' in coast_set:
				tile = GROUND.DEEP_WATER_SOUTHEAST3

		assert tile
		map_db("INSERT INTO ground VALUES(?, ?, ?, ?, ?)", x, y, *tile)

	map_db("COMMIT")
	return map_db


def generate_map(seed = None) :
	"""Generates a whole map.
	@param seed: argument passed to random.seed
	@return filename to the sqlite db containing the new map"""
	rand = random.Random(seed)

	filename = tempfile.mkstemp()[1]
	shutil.copyfile(PATHS.SAVEGAME_TEMPLATE, filename)

	db = DbReader(filename)

	island_space = (35, 35)
	island_min_size = (25, 25)
	island_max_size = (28, 28)

	method = min(2, rand.randint(0, 9)) # choose map creation method with 80% chance for method 2

	if method == 0:
		# generate up to 9 islands
		number_of_islands = 0
		for i in Rect.init_from_topleft_and_size(0, 0, 2, 2):
			if rand.randint(0, 2) != 0: # 2/3 chance for an island here
				number_of_islands = number_of_islands + 1
				x = int( i.x * island_space[0] * (rand.random()/6 + 0.90) )
				y = int( i.y * island_space[1] *  (rand.random()/6 + 0.90) )
				island_seed = rand.randint(-sys.maxint, sys.maxint)
				island_params = {'creation_method': 0, 'seed': island_seed, \
								 'width': rand.randint(island_min_size[0], island_max_size[0]), \
								 'height': rand.randint(island_min_size[1], island_max_size[1])}

				island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

				db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

		# if there is 1 or 0 islands created, it places 1 large island in the centre
		if number_of_islands == 0:
			x = 20
			y = 20
			island_seed = rand.randint(-sys.maxint, sys.maxint)
			island_params = {'creation_method': 1, 'seed': island_seed, \
							 'width': rand.randint(island_min_size[0] * 2, island_max_size[0] * 2), \
							 'height': rand.randint(island_min_size[1] * 2, island_max_size[1] * 2)}
			island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

			db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

		elif number_of_islands == 1:
			db("DELETE FROM island")

			x = 20
			y = 20
			island_seed = rand.randint(-sys.maxint, sys.maxint)
			island_params = {'creation_method': 1, 'seed': island_seed, \
							 'width': rand.randint(island_min_size[0] * 2, island_max_size[0] * 2), \
							 'height': rand.randint(island_min_size[1] * 2, island_max_size[1] * 2)}

			island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

			db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

	elif method == 1:
		# places 1 large island in the centre
		x = 20
		y = 20
		island_seed = rand.randint(-sys.maxint, sys.maxint)
		island_params = {'creation_method': 1, 'seed': island_seed, \
						 'width': rand.randint(island_min_size[0] * 2, island_max_size[0] * 2), \
						 'height': rand.randint(island_min_size[1] * 2, island_max_size[1] * 2)}
		island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

		db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)
	elif method == 2:
		# tries to fill at most land_coefficient * 100% of the map with land
		map_width = 140
		map_height = 140
		min_island_size = 20
		max_island_size = 65
		max_islands = 20
		min_space = 2
		land_coefficient = max(0.3, min(0.6, rand.gauss(0.45, 0.07)))

		islands = []
		estimated_land = 0
		max_land_amount = map_width * map_height * land_coefficient

		for i in xrange(max_islands):
			size_modifier = 1.1 - 0.2 * estimated_land / float(max_land_amount)
			width = rand.randint(min_island_size - 5, max_island_size)
			width = max(min_island_size, min(max_island_size, int(round(width * size_modifier))))
			coef = max(0.25, min(4, rand.gauss(1, 0.2)))
			height = max(min_island_size, min(int(round(width * coef)), max_island_size))
			size = width * height
			if estimated_land + size > max_land_amount:
				continue

			for j in xrange(7):
				# try to place the island 7 times
				x = rand.randint(0, map_width - width)
				y = rand.randint(0, map_height - height)

				rect = Rect.init_from_topleft_and_size(x, y, width, height)
				blocked = False
				for existing_island in islands:
					if rect.distance(existing_island) < min_space:
						blocked = True
						break
				if blocked:
					continue

				island_seed = rand.randint(-sys.maxint, sys.maxint)
				island_params = {'creation_method': 2, 'seed': island_seed, \
								 'width': width, 'height': height}
				island_string = string.Template(_random_island_id_template).safe_substitute(island_params)
				db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

				islands.append(rect)
				estimated_land += size
				break

	return filename

