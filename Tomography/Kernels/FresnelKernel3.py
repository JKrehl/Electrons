from __future__ import division, absolute_import 

import numpy
import numexpr
import scipy.special
import scipy.interpolate
import scipy.ndimage

from ...Utilities import Physics
from ...Mathematics import CoordinateTrafos as CT
from ...Utilities import MemArray as MA
from ...Utilities import Progress
from ...Utilities import Magic
from ...Utilities import HDFArray as HA
from ...Mathematics import FourierTransforms as FT
from ...Mathematics import Interpolator2D

import gc

from .Base import Kernel

def supersample(points, size, factor):
	if factor==1:
		return (lambda e:e.reshape(e.shape+(1,)))(numpy.require(points))
	else:
		return numpy.add.outer(numpy.require(points), size/factor*(numpy.arange(factor)-(factor//2)))
	
def centric_supersample(points, size, factor):
	if factor==1:
		return (lambda e:e.reshape(e.shape+(1,)))(numpy.require(points))
	else:
		return numpy.add.outer(numpy.require(points), size/factor*(numpy.arange(factor)-factor/2+.5))

def create_convolution_kernel(trafo, h, w):
	ss = 32
	size = ss*(2*numpy.ceil(.71*max(h, w))+1)
	window = numpy.ones((ss*h,ss*w))/(h*w)

	trafoc = trafo.copy()
	trafoc.postshift([ss*h/2-.5, ss*w/2-.5])
	trafoc.preshift([-size/2+.5, -size/2+.5])

	window = scipy.ndimage.interpolation.affine_transform(window, trafoc.affine, offset=trafoc.offset, output_shape=(size, size), order=1)

	window = window.reshape(size//ss, ss, size//ss, ss).mean((1,3))
	
	while numpy.all(window[(0,-1),:]==0): window = window[1:-1, :]
	while numpy.all(window[:,(0,-1)]==0): window = window[:, 1:-1]
	
	return window

def segment_interpolate(z, lim):
	z -= numpy.mean(z)
	
	re = numpy.zeros(z.shape, numpy.float64)

	dz = z[1]-z[0]

	mask = z>lim-dz
	re[~mask] = 1
	mask &= z<lim+dz

	sz = supersample(z[mask], dz, 32)
	re[mask] = (sz<lim).mean(1)

	return re/re.mean()
	

def circle_interpolate(y, x, rad):
	y -= numpy.mean(y)
	x -= numpy.mean(x)
	
	re = numpy.zeros(y.shape+x.shape, numpy.float64)
	dy = y[1]-y[0]
	dx = x[1]-x[0]
	r = numexpr.evaluate("sqrt(y**2+x**2)", local_dict=dict(y=y[:,None], x=x[None,:]))
	dr = numpy.sqrt(dy**2+dx**2)/2
	
	mask = r>rad-dr
	re[~mask] = 1
	mask &= r<rad+dr
	
	Y,X = [e[mask] for e in numpy.meshgrid(y,x, indexing='ij')]
	
	sY = supersample(Y, dy, 32)
	sX = supersample(X, dx, 32)
		
	re[mask] = numexpr.evaluate("sqrt(y**2+x**2)<=rad", local_dict=dict(rad=rad, y=sY[:,:,None], x=sX[:,None,:])).mean((1,2))
	
	return re/re.mean()


class FresnelKernel3(Kernel):
	ndims = 3
	dtype=numpy.complex64
	itype=numpy.int32

	def __init__(self, z,y,x,t,d, k, focus=0, bandlimit=0,  mask=None):
		self.__arrays__ = ['dat','idx_td','idx_yx','idz','bounds','z','y','x','t','d','focus','mask']

		self.__dict__.update(dict(z=z, y=y, x=x, t=t, d=d, k=k, bandlimit=bandlimit, focus=focus))

		if not isinstance(self.focus, numpy.ndarray) or self.focus.size==1:
			self.focus = self.focus*numpy.ones(self.t.shape, numpy.obj2sctype(self.focus))
		
		if mask:
			self.mask = numpy.add.outer((numpy.arange(y.size)-y.size//2)**2,(numpy.arange(x.size)-x.size//2)**2).flatten()<(.25*min(y.size**2, x.size**2))
		else:
			self.mask = numpy.ones(y.size*x.size, numpy.bool)

		if self.bandlimit is None:
			self.bandlimit = max(z[1]-z[0], y[1]-y[0], x[1]-x[0])
			
	@property
	def shape(self):
		return self.idz.shape+self.t.shape+self.d.shape+self.idz.shape+self.y.shape+self.x.shape
	
	@property
	def fshape(self):
		return (self.idz.size*self.t.size*self.d.size, self.idz.size*self.y.size*self.x.size)

	def calc(self):
		dw = self.z[1]-self.z[0]
		dv = min(self.y[1]-self.y[0],self.x[1]-self.x[0])
		du = dv

		if self.bandlimit==0:
			self.bandlimit = dw
		
		ss_v = 2
		ss_u = 2
		ss_w = 2
		cutoff = 4e-2
		
		vus = []
		kernels = []
		v_min = numpy.inf
		v_max = -numpy.inf

		for it, ti in Progress(enumerate(self.t), self.t.size, True):
			trafo = CT.Trafo2D().rad(ti)
			v,u,o = trafo.apply_to_bases(self.y,self.x)
			v,u = numexpr.evaluate("v+u+o", local_dict=dict(v=v[:,:,None],u=u[:,None,:],o=o[:,None,None])).reshape(2, self.y.size*self.x.size)
			v -= self.focus[it]
			v_min = min(v_min, numpy.amin(v))
			v_max = max(v_max, numpy.amax(v))
			vus.append((v,u))

			kern = create_convolution_kernel(trafo, ss_v, ss_u)
			kernels.append(kern)

		v_amax = max(-v_min, v_max)
		rho_max = -v_amax*self.bandlimit/dv+numpy.sqrt((v_amax*self.bandlimit/dv)**2+8*numpy.pi*2*v_amax**2/(self.k*dv))
		
		w_i = numpy.arange(-numpy.ceil(rho_max/dw), numpy.ceil(rho_max/dw)+1, dtype=self.itype)
		w = dw*w_i
		v = dv*numpy.arange(numpy.floor(v_min/dv), numpy.ceil(v_max/dv)+1)
		u = du*numpy.arange(-numpy.ceil(rho_max/du), numpy.ceil(rho_max/du)+1)

		w_ss = supersample(w, dw, ss_w).flatten()
		v_ss = supersample(v, dv, ss_v).flatten()
		u_ss = supersample(u, du, ss_u).flatten()
		
		kw_ss = FT.mreciprocal_coords(w_ss)
		ku_ss = FT.mreciprocal_coords(u_ss)

		propf = numexpr.evaluate("1/(2*pi)*exp(-1j*v/(2*k)*(kw**2+ku**2))", local_dict=dict(j=1j, pi=numpy.pi, k=self.k, kw=kw_ss[:,None,None], v=v_ss[None,:,None], ku=ku_ss[None,None,:]))
		
		#res_win = circle_interpolate(kw_ss, ku_ss, numpy.pi/self.bandlimit)
		#res_win = numexpr.evaluate("exp(-.5*dr**2/(pi**2)*(kw**2+ku**2))", local_dict=dict(pi=numpy.pi, kw=kw_ss[:,None], ku=ku_ss[None,:], dr=self.bandlimit/2))
		kr = numexpr.evaluate("sqrt(kw**2+ku**2)*dr", local_dict=dict(kw=kw_ss[:,None], ku=ku_ss[None,:], dr=self.bandlimit, pi=numpy.pi))
		res_win = numexpr.evaluate("where(kr==0, 1, 2*j1kr/kr)", local_dict=dict(pi=numpy.pi, kr=kr, j1kr=scipy.special.j1(kr)))
		#res_win *= FT.mfft(circle_interpolate(w_ss, u_ss, self.bandlimit/2))

		res_win /= numpy.mean(res_win)
		
		propf = numexpr.evaluate("propf*res_win", local_dict=dict(propf=propf, res_win=res_win[:,None,:]))
		
		prop = numpy.empty(w.shape+v_ss.shape+u_ss.shape, self.dtype)
		for i in range(prop.shape[1]):
			prop[:,i,:] = FT.mifft(propf[:,i,:])[ss_w//2::ss_w,:]
			
		del propf
		
		prop_max = numpy.amax(numpy.abs(prop))
		prop_nz = numpy.abs(prop) >= cutoff*prop_max

		prop_shrink = numpy.array([[Magic.where_first(a), Magic.where_last(a)+1] for a in (numpy.any(prop_nz, axis=(1,2)), numpy.any(prop_nz, axis=(0,1)))])
		prop_shrink[0] += [-1,+1]
		prop_shrink[1] += [-ss_u, +ss_u]
		
		if prop_shrink[0,0] < 0: prop_shrink[0,0] = 0
		if prop_shrink[0,1] > prop_nz.shape[0]: prop_shrink[0,1] = prop_nz.shape[0]
		if prop_shrink[1,0] < 0: prop_shrink[1,0] = 0
		if prop_shrink[1,1] > prop_nz.shape[2]: prop_shrink[1,1] = prop_nz.shape[2]
		
		prop = numpy.require(prop[prop_shrink[0,0]:prop_shrink[0,1], :, prop_shrink[1,0]:prop_shrink[1,1]], None, 'O')
		w_i_sh = w_i[prop_shrink[0,0]:prop_shrink[0,1]]
		w_sh = w[prop_shrink[0,0]:prop_shrink[0,1]]
		u_ss_sh = u_ss[prop_shrink[1,0]:prop_shrink[1,1]]
		
		del res_win#, kr
		
		nnc_mask = numpy.count_nonzero(self.mask)
		
		d_idx = numpy.ndarray((self.d.size, nnc_mask), dtype=self.itype)
		d_idx[...] = numpy.mgrid[:self.d.size][:,None]
		d_idx = d_idx.flatten()
		
		yx_idx = numpy.ndarray((self.d.size, nnc_mask), dtype=self.itype)
		yx_idx[...] = numpy.mgrid[:self.y.size*self.x.size][self.mask][None,:]
		yx_idx = yx_idx.flatten()
		
		dat_z = HA.HDFConcatenator(self.dtype)
		td_z = HA.HDFConcatenator(self.itype)
		yx_z = HA.HDFConcatenator(self.itype)
		
		dsel = self.d[d_idx]
		
		for iz, zi in Progress(list(enumerate(w_i_sh)), w_i_sh.size, True):
			
			idat_z = [numpy.ndarray(0, self.dtype)]
			itd_z = [numpy.ndarray(0, self.itype)]
			iyx_z = [numpy.ndarray(0, self.itype)]
			
			for it, ti in Progress(enumerate(self.t), self.t.size):
				
				v,u = vus[it]
				kern = kernels[it]
				
				#propi = scipy.ndimage.filters.convolve(prop[iz,:,:].real, kern, origin=-numpy.array(kern.shape)/2, mode='constant') + \
				#		1j*scipy.ndimage.filters.convolve(prop[iz,:,:].imag, kern, origin=-numpy.array(kern.shape)/2, mode='constant')
				propi = prop[iz,:,:]
				propi_nz = numpy.abs(propi) >= cutoff*prop_max
				
				if numpy.any(propi_nz):
					shrinki = [Magic.where_first(numpy.any(propi_nz, axis=0)), Magic.where_last(numpy.any(propi_nz, axis=0))+1]
					interpi = scipy.interpolate.RegularGridInterpolator((v_ss, u_ss_sh[shrinki[0]:shrinki[1]]), propi[:, shrinki[0]:shrinki[1]], method='linear', bounds_error=False, fill_value=None)
					
					diff_max = max(-u_ss_sh[shrinki[0]], -u_ss_sh[shrinki[1]-1])

					diff = numexpr.evaluate("u-d", local_dict=dict(u=u[yx_idx], d=dsel))
					
					sel = numexpr.evaluate("abs(diff)<=diff_max", local_dict=dict(diff=diff, diff_max=diff_max))
					#sel &= numexpr.evaluate("(d>=ll)&(d<=ul)", local_dict=dict(d=self.d[d_idx], ll=self.d[0]+u_ss_sh[shrinki[1]],  ul=self.d[-1]+u_ss_sh[shrinki[0]]))

					if numpy.any(sel):
						d_sel = d_idx[sel]
						yx_sel = yx_idx[sel]
						diff_sel = diff[sel]
						
						dat = interpi(numpy.vstack((v[yx_sel], diff_sel)).T)
						
						psel = numpy.abs(dat) >= cutoff*prop_max
						
						idat_z.append(numpy.require(dat[psel], requirements='O'))
						itd_z.append(numpy.require(it*self.d.size+d_sel[psel], requirements='O'))
						iyx_z.append(numpy.require(yx_sel[psel], requirements='O'))

						del d_sel, yx_sel, dat, psel

					del shrinki, interpi, diff, sel

				del propi, propi_nz
				del v,u, kern

			dat_z.append(numpy.concatenate(idat_z))
			td_z.append(numpy.concatenate(itd_z))
			yx_z.append(numpy.concatenate(iyx_z))
			del idat_z, itd_z, iyx_z
			
		del prop, yx_idx, d_idx, dsel

		gc.collect()

		self.bounds = [0]+dat_z.sizes
		self.bounds = numpy.cumsum(self.bounds).astype(self.itype)

		self.idz = w_i_sh
		
		#with dat_z.array() as array:
		#	self.dat = numpy.require(array, None, 'O')
		#with td_z.array() as array:
		#	self.idx_td = numpy.require(array, None, 'O')
		#with yx_z.array() as array:
		#	self.idx_yx = numpy.require(array, None, 'O')

		print("data array size: %f %s"%Magic.humanize_filesize(dat_z.size))
		print("td indices array size: %f %s"%Magic.humanize_filesize(td_z.size))
		print("yx indices array size: %f %s"%Magic.humanize_filesize(yx_z.size))
		
		self.dat = dat_z.get_array()
		del dat_z
		self.idx_td = td_z.get_array()
		del td_z
		self.idx_yx = yx_z.get_array()
		del yx_z
		
		return (self.dat, self.idx_td, self.idx_yx, self.idz, self.bounds)
		
	@property
	def idx(self):
		return (self.idx_td, self.idx_yx)
