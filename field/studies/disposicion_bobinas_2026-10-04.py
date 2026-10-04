"""Chequeo exploratorio (2026-10-04, no es un piloto): campo Biot-Savart de tres
disposiciones de las 8 bobinas CREW HaT, para el hallazgo A4 de
docs/bitacora/auditoria_2026-09-30.md.

Filamentos elípticos (semiejes 4 m en z y 2 m en el plano), centros en un
anillo de 8 m, 1e7 A-vuelta por bobina, núcleo regularizado de 0.067 m.
Misma convención que field/generate_ellipse_array.py: la bobina k está en
phi_k = 45°·k y su momento apunta a theta_k en el plano XY.

- K=1 (producción v1):      theta_k = 2 phi_k
- candidata NIAC:           theta_k = 90° - phi_k (orientaciones de la fig. 3.1(b)
                            del reporte NIAC y campo suprimido en el hábitat)
- alternante del ablation:  theta_k = phi_k (k par), phi_k + 90° (k impar)

Solo numpy. Uso: python3 field/studies/disposicion_bobinas_2026-10-04.py
Salida guardada en disposicion_bobinas_2026-10-04.txt.
"""
import numpy as np
mu0=4e-7*np.pi; I=1e7; N=400
def coils(theta_of):
    segs=[]
    for k in range(8):
        ph=k*np.pi/4; th=theta_of(k,ph)
        c=8*np.array([np.cos(ph),np.sin(ph),0]); u=np.array([0,0,1.]); v=np.array([np.sin(th),-np.cos(th),0])
        t=np.linspace(0,2*np.pi,N+1); P=c+4*np.cos(t)[:,None]*u+2*np.sin(t)[:,None]*v
        segs.append(P)
    return segs
def B(pts,segs,a=0.067):
    out=np.zeros_like(pts)
    for P in segs:
        dl=np.diff(P,axis=0); m=(P[1:]+P[:-1])/2
        r=pts[:,None,:]-m[None]; d=np.sqrt((r**2).sum(-1)+a*a)
        out+=mu0*I/(4*np.pi)*(np.cross(dl[None],r)/d[...,None]**3).sum(1)
    return out
pats={'K1 (simulated, th=2phi)':lambda k,ph:2*ph,
      'NIAC candidate (th=90deg-phi)':lambda k,ph:np.pi/2-ph,
      'ablation alternating':lambda k,ph:ph if k%2==0 else ph+np.pi/2}
ang=np.linspace(0,2*np.pi,16,endpoint=False)
for name,f in pats.items():
    s=coils(f)
    c=B(np.array([[0,0,0.]]),s)[0]
    out=[]
    for r in (2,4.5):
        p=np.stack([r*np.cos(ang),r*np.sin(ang),0*ang],1); m=np.linalg.norm(B(p,s),axis=1); out.append(f'r={r}: mean {m.mean():.3f} min {m.min():.3f} max {m.max():.3f}')
    p=np.stack([8*np.cos(ang+np.pi/8),8*np.sin(ang+np.pi/8),0*ang],1); m=np.linalg.norm(B(p,s),axis=1)
    print(f'{name}: |B|(0)={np.linalg.norm(c):.3f} T;', '; '.join(out), f'; between coils r=8: mean {m.mean():.2f}')
