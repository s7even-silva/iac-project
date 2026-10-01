# Replica SampleIsotropicPosition() del C++ (modo cosine y radial) y mide la
# fluencia (longitud de traza por volumen) en esferitas de prueba.
import numpy as np
rng=np.random.default_rng(1); R=6.94; N=4_000_000; r=0.30
def sample(mode):
    ct=2*rng.random(N)-1; st=np.sqrt(1-ct**2); ph=2*np.pi*rng.random(N)
    n=np.c_[st*np.cos(ph),st*np.sin(ph),ct]; pos=n*R
    if mode=='radial': return pos,-n
    ca=np.sqrt(rng.random(N)); sa=np.sqrt(1-ca**2); psi=2*np.pi*rng.random(N)
    # onSphere.orthogonal() de CLHEP: base ortonormal cualquiera perpendicular a n
    a=np.where(np.abs(n[:,[0]])<0.9,[[1,0,0]],[[0,1,0]])
    u=np.cross(n,a); u/=np.linalg.norm(u,axis=1)[:,None]; v=np.cross(n,u)
    d=-ca[:,None]*n+sa[:,None]*(np.cos(psi)[:,None]*u+np.sin(psi)[:,None]*v)
    return pos,d
def fluence(pos,d,c):
    w=pos-c; b=np.sum(w*d,1); q=np.sum(w*w,1)-r*r; disc=b*b-q
    L=np.where(disc>0,2*np.sqrt(np.clip(disc,0,None)),0); L=np.where(-b>0,L,0)  # solo hacia adelante
    return L.sum()/(4/3*np.pi*r**3)
for mode in ('cosine','radial'):
    pos,d=sample(mode); exp=N/(np.pi*R**2)
    print(mode,' '.join(f"x={x}m: {fluence(pos,d,np.array([x,0,0]))/exp:.3f}" for x in (0,1,2,4)),' (1.000 = N/(pi R^2))')
