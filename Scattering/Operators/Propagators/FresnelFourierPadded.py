#!/usr/bin/env python
"""
Copyright (c) 2015 Jonas Krehl <Jonas.Krehl@triebenberg.de>

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

import numpy
import numexpr
from scipy import ndimage
from ....Mathematics import FourierTransforms as FT
from ....Utilities import Physics

from ..Base import IntervalOperator

class FresnelFourierPadded(IntervalOperator):
	def __init__(self, zi, zf, k, kk=None, ky=None, kx=None, y=None, x=None):
		self.__dict__.update(dict(zi=zi,zf=zf, k=k, kk=kk))

		if self.kk is None:
			if ky is None:
				ky = FT.reciprocal_coords(y)
			if kx is None:
				kx = FT.reciprocal_coords(x)
					
			self.kk = numpy.add.outer(ky**2, kx**2)


	def apply(self, wave):
		pad = tuple(i//2 for i in self.kk.shape)
		pshape = tuple(i+2*j for i,j in zip(self.kk.shape, pad))
		scl = tuple(i/j for i,j in zip(self.kk.shape, pshape))
		depad = tuple(slice(i,-i) for i in pad)
		win = numpy.multiply.reduce(numpy.ix_(*tuple(numpy.hamming(i) for i in wave.shape)))
		return FT.ifft(numexpr.evaluate('wave_f*exp(-1j*dis/(2*wn)*kk)', local_dict={'wave_f':FT.fft(numpy.pad(wave*win,pad,mode='constant')), 'pi':numpy.pi, 'dis':self.zf-self.zi, 'wn':self.k,
																					'kk':ndimage.interpolation.affine_transform(self.kk,scl,output_shape=pshape)}))[depad]/win

	def split(self, z):
		return FresnelFourierPadded(self.zi, z, self.k, self.kk), FresnelFourierPadded(z, self.zf, self.k, self.kk)
