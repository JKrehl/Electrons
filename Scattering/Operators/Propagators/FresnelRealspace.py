from __future__ import absolute_import, division

import numpy
import numexpr
import scipy.ndimage
import scipy.optimize

from ....Mathematics import FourierTransforms as FT
from ....Utilities import Physics
from ....Mathematics import get_laplace_kernel

from ..Base import IntervalOperator

class FresnelRealspace(IntervalOperator):
	def __init__(self, zi, zf, k, y=None, x=None, r=1, kernel=None):
		self.__dict__.update(dict(zi=zi,zf=zf, k=k, kernel=kernel))
		if self.kernel is None:
			self.kernel = get_laplace_kernel(r, y[1]-y[0], x[1]-x[0])

	def apply(self, wave):
		laplace = scipy.ndimage.convolve(wave.real, self.kernel, mode='constant', cval=1) + 1j*scipy.ndimage.convolve(wave.imag, self.kernel, mode='constant', cval=0)
		return numexpr.evaluate('wave*exp(-j*dis/(2*k)*laplace)', local_dict=dict(wave=wave, j=1j, pi=numpy.pi, dis=self.zf-self.zi, k=self.k, laplace=laplace))

	def split(self, z):
		return FresnelRealspace(self.zi, z, self.k, kernel=self.kernel), FresnelRealspace(z, self.zf, self.k, kernel=self.kernel)