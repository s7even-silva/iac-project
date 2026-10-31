/* Compiled kernel of compute_field_volumetric.field(): B (T) at npts points
 * from nseg straight current segments, with the exact finite-segment formula
 * outside a uniform round-wire core of radius sqrt(core2) and the linear
 * profile inside it. The NumPy version is memory-bound and barely speeds up
 * with more processes; this loop keeps everything in registers and
 * parallelizes over points with OpenMP. Each point sums its segments in a
 * fixed order, so the result does not depend on the number of threads.
 * Built by compute_field_volumetric.py with plain -O3 (no -ffast-math). */
#include <math.h>
#include <omp.h>

void bs_set_threads(int n) { omp_set_num_threads(n); }

void bs_field(long npts, const double *pts, long nseg, const double *start, const double *dir,
              const double *len, const double *cur, double core2, double *out)
{
#pragma omp parallel for schedule(dynamic, 64)
  for (long p = 0; p < npts; ++p) {
    const double px = pts[3*p], py = pts[3*p+1], pz = pts[3*p+2];
    double bx = 0., by = 0., bz = 0.;
    for (long s = 0; s < nseg; ++s) {
      const double ux = dir[3*s], uy = dir[3*s+1], uz = dir[3*s+2];
      const double rx = px-start[3*s], ry = py-start[3*s+1], rz = pz-start[3*s+2];
      const double cx = uy*rz-uz*ry, cy = uz*rx-ux*rz, cz = ux*ry-uy*rx; /* u x r = u x rho */
      const double q = cx*cx+cy*cy+cz*cz;                                  /* rho^2 */
      const double sp = rx*ux+ry*uy+rz*uz, e = sp-len[s];
      const double f = (sp/sqrt(q+sp*sp+1e-300)-e/sqrt(q+e*e+1e-300))*(cur[s]/(q > core2 ? q : core2));
      bx += f*cx; by += f*cy; bz += f*cz;
    }
    out[3*p] = bx*1e-7; out[3*p+1] = by*1e-7; out[3*p+2] = bz*1e-7; /* mu0/(4 pi) */
  }
}
