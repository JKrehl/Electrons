from __future__ import division, generators

import numpy
import numexpr

from scipy import ndimage

from . import CoordinateTrafos as CT

class VolumeTrafo3D:

	def __init__(self, trafo, shape, tshape, origin='center'):
		assert isinstance(trafo, CT.Trafo3D)
		self.trafo = trafo.inv

		self.shape = shape
		self.tshape = tshape
		
		self.origin = origin

		self.idxtrafo = self.trafo.copy()
		
		if self.origin == 'center':
			self.idxtrafo.add_preshift([-i//2 for i in self.shape])
			self.idxtrafo.add_postshift([i//2 for i in self.tshape])
		elif self.origin == 'zero':
			pass
		else:
			raise AttributeError

		tzyxo = self.idxtrafo.inv.apply_to_bases(*tuple(numpy.arange(i) for i in self.shape))
		self.proj_coords = numexpr.evaluate('x+y+z+o', local_dict=dict(z=tzyxo[0][:,:,None,None], y=tzyxo[1][:,None,:,None], x=tzyxo[2][:,None,None,:], o=tzyxo[3][:,None,None,None]))

		zyxo = self.idxtrafo.apply_to_bases(*tuple(numpy.arange(i) for i in self.tshape))
		self.bproj_coords = numexpr.evaluate('x+y+z+o', local_dict=dict(z=zyxo[0][:,:,None,None], y=zyxo[1][:,None,:,None], x=zyxo[2][:,None,None,:], o=zyxo[3][:,None,None,None]))

	def apply_to(self, a):
		return ndimage.interpolation.map_coordinates(a, self.proj_coords, order=1)
    
	def apply_fro(self, a):
		return ndimage.interpolation.map_coordinates(a, self.bproj_coords, order=1)