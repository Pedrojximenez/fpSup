/* Presentation data only. These dimensions are editable examples, not a camera capability table. */
const qsRecording = (()=>{
  const formats=['MOV','CDNG 8bit','CDNG 10bit','CDNG 12bit','CDNG 14bit'];
  const ratios=['3:2','16:9','4:3','1:1','2.39:1'];
  const dcPresets={OG:[6000,4000,'3:2'],HD:[6000,3375,'16:9'],S35:[4000,2250,'16:9'],'APS-C':[4000,2667,'3:2']};
  const widths={'1K':1024,'2K':2048,'3K':3072,'3.5K':3584,'4K':4096};
  const limit=16384;
  // Approximate preview calibration: official fp sensor size mapped to this preview's OG example.
  // https://www.sigma-global.com/en/cameras/fp/?local=table&tab=support&table_id=11934
  const sensor={widthMm:35.9,heightMm:23.9,widthPx:6000,heightPx:4000};
  const pixel=n=>Number.isInteger(n) && n>=1 && n<=limit;
  const clone=s=>({format:s.format,dc:{...s.dc},res:{...s.res}});
  const fraction=ratio=>ratio.split(':').map(Number);
  function ratioOf(width,height) {
    for (const ratio of ratios) {
      const [w,h]=fraction(ratio);
      if (width*h===height*w) return ratio;
    }
    for (const ratio of ratios) {
      const [w,h]=fraction(ratio);
      if (Math.abs(width/height-w/h)/(w/h)<=0.00025 &&
        (height===Math.round(width*h/w) || width===Math.round(height*w/h))) return ratio;
    }
    // Keep familiar aspects above; other windows use cinema-style decimal notation.
    // Two decimal places normally suffice. Retain significant digits for tiny portrait windows.
    const aspect=width/height;
    return `${aspect<0.01 ? Number(aspect.toPrecision(2)) : aspect.toFixed(2)}:1`;
  }
  function dcPreset(width,height) {
    return Object.keys(dcPresets).find(key=>dcPresets[key][0]===width && dcPresets[key][1]===height) || '自訂';
  }
  function customLabel(size) { return `CUSTOM(${ratioOf(size.width,size.height)})`; }
  function dcLabel(s) { return s.dc.preset==='自訂' ? customLabel(s.dc) : s.dc.preset; }
  function cropMm(s) {
    return {width:Number((s.dc.width/sensor.widthPx*sensor.widthMm).toFixed(2)),
      height:Number((s.dc.height/sensor.heightPx*sensor.heightMm).toFixed(2))};
  }
  function fit(width,height,ratio,anchor='width',maxWidth=limit,maxHeight=limit) {
    const pair=fraction(ratio);
    if (pair) {
      if (anchor==='height') width=Math.max(1,Math.round(height*pair[0]/pair[1]));
      else height=Math.max(1,Math.round(width*pair[1]/pair[0]));
      if (width>maxWidth) { width=maxWidth; height=Math.max(1,Math.round(width*pair[1]/pair[0])); }
      if (height>maxHeight) { height=maxHeight; width=Math.max(1,Math.round(height*pair[0]/pair[1])); }
    }
    return {width,height,ratio:ratioOf(width,height)};
  }
  function resOptions(s) {
    const list=Object.keys(widths).filter(key=>{
      const size=resSize(s,key); return size.width<=s.dc.width && size.height<=s.dc.height;
    }).map(key=>s.dc.preset==='HD' && key==='2K' ? 'FHD (2K)' : s.dc.preset==='HD' && key==='4K' ? 'UHD (4K)' : key);
    if (s.res.preset==='自訂') list.push(resLabel(s));
    return list;
  }
  function resLabel(s) {
    if (s.res.preset==='自訂') return customLabel(s.res);
    return s.dc.preset==='HD' && s.res.preset==='2K' ? 'FHD (2K)' :
      s.dc.preset==='HD' && s.res.preset==='4K' ? 'UHD (4K)' : s.res.preset;
  }
  function resSize(s,key) {
    const hd=s.dc.preset==='HD';
    const width=hd && key==='2K' ? 1920 : hd && key==='4K' ? 3840 : widths[key];
    const height=Math.max(1,Math.round(width*s.dc.height/s.dc.width));
    return {width,height,ratio:ratioOf(width,height)};
  }
  function constrainRes(s) {
    const width=Math.min(s.res.width,s.dc.width),height=Math.min(s.res.height,s.dc.height);
    const clipped=width!==s.res.width || height!==s.res.height;
    s.res={preset:clipped ? '自訂' : s.res.preset,width,height,ratio:ratioOf(width,height)};
  }
  function deriveRes(s) {
    if (s.res.preset!=='自訂') s.res={preset:s.res.preset,...resSize(s,s.res.preset)};
    constrainRes(s);
  }
  function defaults() {
    const s={format:'CDNG 12bit',dc:{preset:'OG',...fit(6000,4000,'3:2')},res:{preset:'3K'}};
    deriveRes(s); return s;
  }
  function restore(raw,legacy=[]) {
    const s=defaults();
    if (!raw || typeof raw!=='object') {
      s.format=legacy[6]==='MOV' ? 'MOV' : formats.includes(legacy[6]) ? legacy[6] : s.format;
      if (['FHD','UHD'].includes(legacy[4])) {
        s.dc={preset:'HD',...fit(...dcPresets.HD)};
        s.res.preset=legacy[4]==='FHD' ? '2K' : '4K';
      } else if (Object.hasOwn(widths,legacy[4])) s.res.preset=legacy[4];
      deriveRes(s); return s;
    }
    if (formats.includes(raw.format)) s.format=raw.format;
    for (const kind of ['dc','res']) {
      const d=raw[kind],validPreset=kind==='dc' ? [...Object.keys(dcPresets),'自訂'] : [...Object.keys(widths),'自訂'];
      if (d && validPreset.includes(d.preset) && pixel(d.width) && pixel(d.height)) {
        // Dimensions are authoritative, including old records whose ratio was stale or "自由".
        s[kind]={preset:d.preset,width:d.width,height:d.height,ratio:ratioOf(d.width,d.height)};
      }
    }
    s.dc.preset=dcPreset(s.dc.width,s.dc.height);
    deriveRes(s); return s;
  }
  function select(state,kind,value) {
    const s=clone(state);
    if (kind==='format') { if (formats.includes(value)) s.format=value; }
    else if (kind==='dc' && Object.hasOwn(dcPresets,value)) {
      s.dc={preset:value,...fit(...dcPresets[value])}; deriveRes(s);
    } else if (kind==='res') {
      const key=value==='FHD (2K)' ? '2K' : value==='UHD (4K)' ? '4K' : value;
      if (Object.hasOwn(widths,key) && resOptions(s).includes(value)) { s.res.preset=key; deriveRes(s); }
    }
    return s;
  }
  function dimension(state,kind,field,value) {
    if (!['dc','res'].includes(kind) || !['width','height','ratio'].includes(field)) return state;
    if (field==='ratio' ? !ratios.includes(value) : !pixel(value)) return state;
    const s=clone(state),d={...s[kind],[field]:value};
    const size=field==='ratio' ? fit(d.width,d.height,value,'width',kind==='res' ? s.dc.width : limit,kind==='res' ? s.dc.height : limit) :
      {width:d.width,height:d.height,ratio:ratioOf(d.width,d.height)};
    s[kind]={preset:kind==='dc' ? dcPreset(size.width,size.height) : '自訂',...size};
    if (kind==='dc') deriveRes(s); else constrainRes(s);
    return s;
  }
  return {formats,ratios,dcOptions:Object.keys(dcPresets),limit,defaults,restore,select,dimension,resOptions,resLabel,ratioOf,dcLabel,cropMm};
})();
