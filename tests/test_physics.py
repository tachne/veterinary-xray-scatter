"""The angular and layer expectations here use independent quadrature and geometry."""
import csv
from dataclasses import replace
from numpy.polynomial.legendre import leggauss
import numpy as np
import pytest

from scatter.model import (AIR, BODY, BLADE, MIRROR, COVER, FILTER, TABLE, COHERENT, COMPTON, PHOTO,
                           ENERGY_NAMES, DATA, ENERGIES, Settings, coefficients, energy_after, material_data,
                           probability, rotate, sample_kn, simulate)
from scatter.results import summary


@pytest.mark.parametrize("e", [30,80,150])
def test_energy_and_momentum_conservation(e):
    cs=np.array([1., 0., -1.])
    es=energy_after(e,cs)
    np.testing.assert_allclose(es,[e,511*e/(511+e),511*e/(511+2*e)])
    t=e-es
    np.testing.assert_allclose(t*(t+1022),e*e+es*es-2*e*es*cs,atol=1e-10)
    assert (t>=0).all()


@pytest.mark.parametrize("e",[30,80,150])
def test_kn_distribution_against_solid_angle_integral(e):
    # Integrate dσ/dΩ * sinθ dθ in θ; sampling actually uses cosθ.
    rng=np.random.default_rng(1397)
    c=sample_kn(e,120000,rng)
    theta=np.degrees(np.arccos(c))
    edges=np.linspace(0,180,13)
    x,w=leggauss(24)
    probs=[]
    for a,b in zip(np.radians(edges[:-1]),np.radians(edges[1:])):
        t=(x+1)*(b-a)/2+a
        ratio=511/(511+e*(1-np.cos(t)))
        probs.append(np.dot(w,ratio**2*(ratio+1/ratio-np.sin(t)**2)*np.sin(t))*(b-a)/2)
    probs=np.array(probs)/sum(probs)
    measured=np.histogram(theta,bins=edges)[0]
    assert np.max(abs(measured-probs*len(c))/np.sqrt(len(c)*probs*(1-probs))) < 5.2
    assert np.all((c>=-1)&(c<=1))


def test_rotation_in_three_dimensions_about_actual_incident_ray():
    inc=np.array([[0.,0.,1.],[.2,.3,1.],[-.3,.1,1.]])
    inc/=np.linalg.norm(inc,axis=1)[:,None]
    c=np.array([-1.,.37,0.])
    out=rotate(inc,c,np.array([0.,1.17,2.3]))
    np.testing.assert_allclose(np.sum(out*inc,axis=1),c,atol=1e-14)
    np.testing.assert_allclose(np.linalg.norm(out,axis=1),1)
    np.testing.assert_allclose(out[0],-inc[0])


def test_published_xcom_values_and_lead_k_edge():
    with (DATA/"xcom.csv").open() as f:
        data=list(csv.DictReader(f))
    assert len(data)==66 and len(set((r["material"],r["energy_keV"]) for r in data))==66
    assert coefficients("water",80)==(.1697,.00577,.008165,.1837)
    assert coefficients("air",80)==(.1523,.005912,.008028,.1662)
    assert coefficients("pb",85)[3]==2.081 and coefficients("pb",90)[3]==7.256
    for name,m in material_data().items():
        assert sum(m["fractions"].values())==pytest.approx(1,abs=2e-6)
        for e in ENERGIES:
            xs=coefficients(name,e)
            assert min(xs)>0 and sum(xs[:3])==pytest.approx(xs[3],rel=.00045)
    with pytest.raises(ValueError): coefficients("pb",88)


def test_density_and_thickness_via_known_air_and_water_slabs():
    air=material_data()["air"]["density"]
    assert air==.00120479
    assert probability(.1662,air,100)==pytest.approx(1-np.exp(-.0200236098))
    assert probability(.1837,1,0)==0
    p=probability(.1837,1,5)
    assert probability(.1837,2,5)==pytest.approx(1-(1-p)**2)
    assert probability(.1837,2,5)==probability(.1837,1,10)


def analytical_rates(params):
    # Independent midpoint quadrature in the positive detector quadrant, weighted in area.
    # Split at the blade opening so that the step is integrated exactly.
    edges=(0.,params.field/2,20.)
    names=("air","water","pc","pb","al","pmma","al")
    mus=np.array([coefficients(k,params.energy)[3]*material_data()[k]["density"] for k in names])
    weights=np.zeros(8)
    for i,(a,b) in enumerate(zip(edges,edges[1:])):
        for j,(d,e) in enumerate(zip(edges,edges[1:])):
            nx=40
            q=a+(np.arange(nx)+.5)*(b-a)/nx
            z=d+(np.arange(nx)+.5)*(e-d)/nx
            sec=np.sqrt(1+(q[:,None]/100)**2+(z[None,:]/100)**2)
            alive=np.ones_like(sec)
            spatial=(b-a)*(e-d)/400
            # Independent list of layer thicknesses (cm), not model.layers().
            sequence=((AIR,5),(FILTER,.1),(AIR,2.9),(MIRROR,.04),(AIR,2.96),
                      (BLADE if i or j else AIR,.3),(AIR,3.7),(COVER,.2),
                      (AIR,77.8-params.thickness),(BODY,params.thickness),(TABLE,1),(AIR,6))
            for k,width in sequence:
                after=alive*np.exp(-mus[k]*width*sec)
                weights[k]+=spatial*(alive-after).mean()
                alive=after
            weights[7]+=spatial*alive.mean()
    assert weights.sum()==pytest.approx(1,abs=1e-13)
    return weights


@pytest.mark.parametrize("energy,thickness,field",[(30,0,6),(80,12,24),(150,30,36)])
def test_first_collisions_per_part_and_process_agree_with_xcom(energy,thickness,field):
    p=Settings(energy,thickness,field,85000,942)
    r=simulate(p)
    expected=analytical_rates(p)
    actual=np.bincount(np.where(r.part==-1,7,r.part),minlength=8)
    assert np.all(abs(actual-p.count*expected)<5.6*np.sqrt(p.count*expected*(1-expected))+1)
    for k,name in enumerate(("air","water","pc","pb","al","pmma","al")):
        if not actual[k]:continue
        part=np.array(coefficients(name,energy)[:3]); b=part/part.sum()
        counts=np.bincount(r.process[r.part==k],minlength=4)[1:]
        assert np.all(abs(counts-actual[k]*b)<5.5*np.sqrt(actual[k]*b*(1-b))+1)
    rows=summary(r)
    assert sum(s["interactions"] for s in rows)+actual[-1]==p.count
    assert rows[2]["entered"]==np.any(r.entered[:,3:],axis=1).sum()
    assert rows[3]["entered"]==p.count and all(s["entered"]>=s["interactions"] for s in rows)
    assert sum(s["compton"] for s in rows)==(r.process==COMPTON).sum()
    assert all(s["interactions"]==s["compton"]+s["photoelectric"]+s["coherent"] for s in rows)
    if thickness==0:assert rows[0]["entered"]==rows[0]["interactions"]==0


def test_spatial_boundaries_and_sides_of_field():
    p=Settings(count=50000)
    r=simulate(p); x,y,z=r.position.T
    assert np.all((z>=0)&(z<=100))
    np.testing.assert_allclose(x,z*r.incident[:,0]/r.incident[:,2],atol=2e-14)
    blocked=np.max(abs(r.incident[:,:2]),axis=1)/r.incident[:,2] > p.field/200
    for k,lo,hi in ((BODY,81,93),(TABLE,93,94),(FILTER,5,5.1),(MIRROR,8,8.04),
                    (BLADE,11,11.3),(COVER,15,15.2)):
        m=r.part==k
        assert m.any() and np.all((z[m]>=lo)&(z[m]<hi)) and r.entered[m,k].all()
    assert blocked[r.part==BLADE].all() and np.all(z[r.part==-1]==100)
    scattered=r.process==COMPTON
    np.testing.assert_allclose((r.outgoing[scattered]*r.incident[scattered]).sum(axis=1),
                               r.cosine[scattered],atol=1e-14)
    assert np.isnan(r.scattered_energy[~scattered]).all() and np.isnan(r.outgoing[~scattered]).all()


def test_repeatable_and_opening_and_thickness_change_expected_counts():
    p=Settings()
    r,t=simulate(p),simulate(p)
    for k in ("part","process","position","outgoing","scattered_energy","cosine"):
        np.testing.assert_array_equal(getattr(t,k),getattr(r,k))
    assert not np.array_equal(simulate(replace(p,seed=43)).position,r.position)
    bigger=simulate(replace(p,field=36))
    assert bigger.entered[:,BLADE].sum()<r.entered[:,BLADE].sum()
    assert bigger.entered[:,BODY].sum()>r.entered[:,BODY].sum()
    thicker=simulate(replace(p,thickness=27))
    assert (thicker.part==BODY).sum()>(r.part==BODY).sum()
    assert (thicker.part==-1).sum()<(r.part==-1).sum()


def test_sample_uncertainty_decreases_over_independent_seeds():
    actual=[]
    for n in (1200,19200):
        actual.append(np.std([np.mean(simulate(Settings(count=n,seed=s)).part==AIR)
                              for s in range(32)],ddof=1))
    assert .12 < actual[1]/actual[0] < .45  # predicted 1/sqrt(16) = 0.25, noisy 32-seed estimate


@pytest.mark.parametrize("bad",[{"energy":87},{"field":0},{"thickness":31},{"count":0},{"seed":-1}])
def test_reject_unsupported_values(bad):
    with pytest.raises(ValueError): Settings(**bad)
