import numpy
import scipy.sparse
import pyximport
pyximport.install()

from contextlib import contextmanager

from ..Kernels import Kernel
from . import StackedExtendedProjector_cython as cython

class StackedExtendedProjector(scipy.sparse.linalg.LinearOperator):
	def __init__(self, kernel, z, threads=0):
		self.z = z

		self.kernel = kernel
		self.dtype = kernel.dtype
		self.itype = kernel.itype

		with self.kernel.open():
			shp = self.kernel.shape
		self.shape = (self.z.size*shp[1]*shp[2], self.z.size*shp[4]*shp[5])

		
		self.threads = threads
		
		self.matvec = self._matvec
		self.rmatvec = self._rmatvec

	@contextmanager
	def in_memory(self):
		with self.kernel.in_memory('dat', 'row', 'col', 'idz', 'bounds'):
			yield

	def _matvec(self, v):
		v = v.reshape(self.shape[1])
		
		u = numpy.zeros(self.shape[0], self.dtype)

		with self.in_memory():
			cython.matvec(v,u, self.z.size, self.kernel.idz, self.kernel.bounds, self.kernel.col, self.kernel.row, self.kernel.dat, self.threads)

		return u
	
	def _rmatvec(self, v):
		v = v.reshape(self.shape[0])

		u = numpy.zeros(self.shape[1], self.dtype)
		
		with self.in_memory():
			cython.matvec(v,u, self.z.size, -self.kernel.idz, self.kernel.bounds, self.kernel.row, self.kernel.col, self.kernel.dat, self.threads)

		return u