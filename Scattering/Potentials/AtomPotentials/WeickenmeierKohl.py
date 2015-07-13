 
from __future__ import division, print_function, absolute_import

import numpy
from scipy import special
import numexpr
from ....Utilities import FourierTransforms as FT
from .Base import AtomPotentialGenerator

import functools
import os.path
__dir__ = os.path.dirname(os.path.abspath(__file__))

class WeickenmeierKohlClass(AtomPotentialGenerator):
	def __init__(self):
		self.coeff = {int(i[0]):i[1:] for i in numpy.loadtxt(__dir__+"/parameters/weickenmeier_kohl_coefficients.dat")}

	def form_factors_k(self, Z, *k):
		kk = functools.reduce(numpy.add.outer,tuple((numpy.require(i))**2 for i in k), 0)
		A1 = (16*numpy.pi**2)*2.395e8*Z/(3.+3.*self.coeff[Z][0])
		A4 = self.coeff[Z][0]*A1
		B = self.coeff[Z][1:7]
	
		mss = kk!=0
		re = numpy.empty(kk.shape,type(A1))
		re[mss] = numexpr.evaluate("(A1*(1-exp(-B1*kk))/kk+A1*(1-exp(-B2*kk))/kk+A1*(1-exp(-B3*kk))/kk+A4*(1-exp(-B4*kk))/kk+A4*(1-exp(-B5*kk))/kk+A4*(1-exp(-B6*kk))/kk)",
								   local_dict=dict(kk=kk[mss], A1=A1,A4=A4,B1=B[0],B2=B[1],B3=B[2],B4=B[3],B5=B[4],B6=B[5]))
		re[~mss] = (A1*B[0]+A1*B[1]+A1*B[2]+A4*B[3]+A4*B[4]+A4*B[5])

		return re

	def form_factors_r(self, Z, *x):
		r = numpy.sqrt(functools.reduce(numpy.add.outer,tuple(numpy.require(i)**2 for i in x), 0))

		A1 = (16*numpy.pi**2)*2.395e8*Z/(3.+3.*self.coeff[Z][0])
		A4 = self.coeff[Z][0]*A1
		B = self.coeff[Z][1:7]

		res = numexpr.evaluate('1/(pi**3*8)*2*pi**2/r*(A1*(ErfcB1+ErfcB2+ErfcB3)+A4*(ErfcB4+ErfcB5+ErfcB6))',
							   local_dict=dict(r=r, pi=numpy.pi,A1=A1,A4=A4,
											   ErfcB1=special.erfc(.5*r/numpy.sqrt(B[0])),
											   ErfcB2=special.erfc(.5*r/numpy.sqrt(B[1])),
											   ErfcB3=special.erfc(.5*r/numpy.sqrt(B[2])),
											   ErfcB4=special.erfc(.5*r/numpy.sqrt(B[3])),
											   ErfcB5=special.erfc(.5*r/numpy.sqrt(B[4])),
											   ErfcB6=special.erfc(.5*r/numpy.sqrt(B[5]))))
		res[r==0] = 1/(numpy.pi**3*8)*2*numpy.pi**2*(A1*3+A4*3)/2

		return res
		
		
WeickenmeierKohl = WeickenmeierKohlClass()
