#cython: boundscheck=False, initializedcheck=False, wraparound=False

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

cimport numpy
from cython.parallel cimport parallel, prange
cimport openmp

numpy.import_array()

from ...Utilities.Projector_Utilities cimport itype, dtype, atomic_add

def matvec(
		dtype[:] vec,
		dtype[:] res,
		dtype[:] dat,
		itype[:] row,
		itype[:] col,
		int threads = 0,
		):

	cdef numpy.npy_intp tensor_length = dat.size
	cdef numpy.npy_intp i
	cdef dtype tmp

	if threads==0:
		threads = openmp.omp_get_max_threads()
	
	with nogil, parallel(num_threads=threads):
		for i in prange(tensor_length, schedule='guided'):
			tmp = dat[i]*vec[col[i]]
			atomic_add(&res[row[i]], tmp)
