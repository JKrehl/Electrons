from __future__ import absolute_import, division

import numpy
from ..Operators import OperatorChain
from ..Operators.TransferFunctions import FlatAtomDW
from ..Operators.Propagators import FresnelFourier
from ..Potentials.AtomPotentials import Kirkland
from ...Utilities import FourierTransforms as FT

class Multislice:
	def __init__(self, x, y, potential, energy, zi=None, zf=None, trafo=None, atom_potential_generator=Kirkland, transfer_function=FlatAtomDW, propagator=FresnelFourier):
		self.__dict__.update(dict(x=x, y=y, energy=energy,
								  zi=zi, zf=zf, trafo=trafo,
								  atom_potential_generator=atom_potential_generator, transfer_function=transfer_function, propagator=propagator))
		self.prepared = False
		
		if self.trafo is not None:
			self.potential = potential.transform(self.trafo)
		else:
			self.potential = potential.copy()
		self.potential.zsort()

		if self.zf is None:
			self.zf = self.potential.zmax()
		if self.zi is None:
			self.zi = self.potential.zmin()
		
	def prepare(self):
		self.opchain = OperatorChain(zi=self.zi, zf=self.zf)

		phaseshifts_f = {Z:self.atom_potential_generator.phaseshift_f(Z, self.energy, self.x, self.y) for Z in numpy.unique(self.potential.atoms['Z'])}

		kx, ky = FT.reciprocal_coords(self.x, self.y)
		kk =  numpy.add.outer(kx**2, ky**2)
		
		for i in xrange(self.potential.atoms.size):
			self.opchain.append(self.transfer_function(self.x, self.y, self.potential.atoms[i:i+1], kx=kx, ky=ky, kk=kk, phaseshifts_f=phaseshifts_f, lazy=True)) 

		for zi, zf in self.opchain.get_gaps():
			self.opchain.append(self.propagator(zi,zf, self.energy, kx, ky, kk))

		self.opchain.impose_zorder()
		
		self.prepared = True
		
	def run(self, wave=None):
		if wave is None:
			wave = numpy.ones(self.x.shape+self.y.shape, dtype=numpy.complex)
	
		if not self.prepared:
			self.prepare()

		for op in self.opchain['operator']:
			wave = op.apply(wave)

		return wave