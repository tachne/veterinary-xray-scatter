// No fictitious space after the grid. A guide is a fixed LENGTH IN SCREEN UNITS,
// rooted at a recorded PASS on the detector, never an additional physical endpoint.
export const RAY_INK = Object.freeze({primary:"#176c75", scatter:"#aa521c"});
export function directionGuide(e, origin, length) {
  if (!e.entry || e.gridCode!==4) return null;
  const [x,z]=e.xzDirection, norm=Math.hypot(x,z);
  if (!(z>0) || !Number.isFinite(norm)) return null;
  return [origin[0]+length*x/norm,origin[1]+length*z/norm];
}

// Both room panes use the same isotropic x–z camera up to the detector.
// Beyond it we reserve screen space, including room for a near-horizontal guide
// starting at either outer edge of the detector. No fictitious z is assigned.
export function focusedRoomLayout(width, bounds, geometry) {
  const [leftCm, rightCm, topCm] = bounds;
  const leftMargin = width < 280 ? 23 : 31;
  const rightMargin = 10;
  const top = 26;
  const plotWidth = width - leftMargin - rightMargin;
  const guideLength = Math.min(130, plotWidth * 0.28);
  const depth = geometry.sid - topCm;
  const maxRoomHeight = Math.min(465, width * 1.3 + 60);
  const scale = Math.min(
    plotWidth / (rightCm - leftCm),
    (plotWidth - 2 * (guideLength + 3)) / (2 * geometry.halfWidth),
    maxRoomHeight / depth
  );
  const centerX = leftMargin + plotWidth / 2;
  const detectorY = top + depth * scale;
  const height = Math.ceil(detectorY + guideLength + 28);
  const project = (x, z) => [centerX + x * scale, top + (z - topCm) * scale];
  return {width, height, guideLength, project, detectorY, top, scale};
}

// The left ray supplies a common wavefront. A right-hand ray that hits lead
// stays at the first contact while the unobstructed left ray continues.
export function syncedGridPhase(off,on,phase) {
  if (!on.entry || on.gridCode!==5 || phase<.82) return phase;
  const offEnd=off.exit||off.end, onEnd=on.exit||on.end;
  const dz=offEnd[2]-off.entry[2];
  const fraction=dz>0 ? Math.min(1, Math.max(0,(onEnd[2]-on.entry[2])/dz)) : 0;
  return fraction>0 ? Math.min(1,.82+(phase-.82)/fraction) : 1;
}
export function localCamera(g, off, on) {
  const center=off.entry[0], half=Math.max(.085,g.height*.65);
  const ends=[off.approach, off.exit||off.end,on.exit||on.end].map(p=>p[0]);
  const left=Math.max(-g.halfWidth,Math.min(center-half,...ends.map(x=>x-g.gap)));
  const right=Math.min(g.halfWidth,Math.max(center+half,...ends.map(x=>x+g.gap)));
  const scale=Math.min(308/(right-left),104/(1.22*g.height));
  return {left,right,scale,point:(x,z)=>[170+(x-(left+right)/2)*scale,142+(z-g.sid)*scale]};
}
