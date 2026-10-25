(() => {
  // QS_MOTION_CORE
  // QS_RECORDING_MODEL
  const root = document.getElementById('fp-touch-qs');
  const screen = root.querySelector('.screen'), panel = root.querySelector('.panel');
  const qsContent=root.querySelector('.qs-content');
  const grid = root.querySelector('.grid'), catalog = root.querySelector('.catalog');
  const gridViewport = root.querySelector('.grid-viewport');
  const catalogViewport = root.querySelector('.catalog-viewport');
  const options = root.querySelector('.inline-options'), optionTrack = root.querySelector('.option-track'), ghost = root.querySelector('.ghost');
  const rowDivider = root.querySelector('.row-divider');
  const title = root.querySelector('.title'), live = root.querySelector('[aria-live]');
  const backdrop = root.querySelector('.backdrop'), adjustbar = root.querySelector('.adjustbar');
  const backgroundControls = root.querySelector('.background-controls'), opacityInput = root.querySelector('#fp-qs-opacity');
  const opacityOutput = backgroundControls.querySelector('output'), editCaption = root.querySelector('.edit-caption');
  const trash=root.querySelector('.trash-drop'),trashLabel=trash.querySelector('span');
  const dimensionGrid=root.querySelector('.dimension-grid'), dimensionControls=root.querySelector('.dimension-controls');
  const dimensionInput=dimensionControls.querySelector('[type="number"]'),dimensionRange=dimensionControls.querySelector('[type="range"]');
  const pageLabel = root.querySelector('.page-label'), edgeButton = root.querySelector('.edge');
  const actions = Object.fromEntries(Array.from(root.querySelectorAll('[data-action]')).map(b=>[b.dataset.action,b]));
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const NO_ANIMATION = true;
  root.dataset.motion='none';
  const metrics = {pointerUpdates:0,boundsReads:0,draws:0,valueWrites:0,optionNodes:5,wheelEvents:0,scrollEvents:0};
  const tileParts = [], flashTimers = new Map();
  const items = [
    ['ISO','800',['100','200','400','800','1600','3200','6400'],'ISO'],
    ['快門角度','180°',['45°','90°','144°','172.8°','180°','270°','360°'],'SHUTTER'],
    ['光圈','F2.8',['F1.8','F2','F2.8','F4','F5.6','F8'],'IRIS'],
    ['白平衡','5600 K',['自動','3200 K','4300 K','5000 K','5600 K','6500 K'],'WB'],
    ['解析度','3K',['1K','2K','3K','3.5K','4K'],'RES'],
    ['格率','29.97p',['23.98p','24p','25p','29.97p'],'FPS'],
    ['錄影格式','CDNG 12bit',qsRecording.formats,'FORMAT'],
    ['音訊增益','−12 dB',['−24 dB','−18 dB','−12 dB','−6 dB','0 dB'],'AUDIO'],
    ['斑馬紋','關',['關','開'],'ZEBRA'], ['峰值對焦','開',['關','開'],'PEAKING'],
    ['假色','關',['關','開'],'FALSE COLOR'], ['波形','關',['關','開'],'WAVEFORM'],
    ['對焦模式','MF',['MF','AF'],'FOCUS'], ['對焦區域','單點',['單點','區域','追蹤'],'FOCUS AREA'],
    ['色彩模式','OFF',['OFF','標準','中性','TEAL & ORANGE'],'COLOR'],
    ['耳機音量','3',['0','1','2','3','4','5'],'HEADPHONE'], ['格線','關',['關','開'],'GRID'],
    ['水平儀','關',['關','開'],'LEVEL'], ['螢幕亮度','自動',['自動','1','2','3','4','5','6','7'],'LCD'],
    ['電子防手震','關',['關','開'],'EIS'],
    ['裁切範圍','OG',qsRecording.dcOptions,'DC']
  ];
  const toggles = new Set([8,9,10,11,16,17,19]);
  // Keep existing identities, including the user's waveform item; append DC as id 20.
  let ids = [0,1,2,4,5,6,20,3,7,10,11], values = items.map(i => i[1]);
  let recording=qsRecording.defaults(),customScope=null,dimensionField='width';
  let dimensionTransition=null;
  let mode = 'closed', page = 0, catalogPage = 0, selected = ids[0], reveal = 0;
  let editing = false, active = null, timer = 0, edgeTimer = 0, lastTap = null;
  let suppressed = new Set(), lastOrder = '';
  let backgroundAlpha4 = 7, backgroundEditing = false, lastAdjustKey = '';
  let moveFrame = 0, pendingPoint = null, pendingPersist = null, persistHandle = null;
  let revealAdjacent = false, pageMotion = null, pageFrame = 0, valueAnimation = null, pageDragPx = 0;
  let catalogKey = '', motionTrace = [];
  let gridWidth=0,gridScrolling=false,gridEndTimer=0,gridWheel=null,wheelFrame=0;
  const checkMotion = root.hasAttribute('data-qs-motion-check');
  const gridPages=Array.from({length:3},()=>{
    const group=document.createElement('div'); group.className='qs-page'; grid.append(group); return group;
  });
  const optionButtons = Array.from({length:5},()=>{
    const b=document.createElement('button'); b.type='button'; b.className='cursor-interaction'; optionTrack.append(b); return b;
  });
  const tiles = items.map((item,id) => {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'tile cursor-interaction'; b.dataset.item = id;
    for (const [name,text] of [['label',item[3]],['value',values[id]],['subvalue','']]) {
      const span = document.createElement('span'); span.className = name; span.textContent = text; b.append(span);
    }
    tileParts[id] = {value:b.children[1],subvalue:b.children[2]};
    gridPages[0].append(b); return b;
  });
  function say(text) { live.textContent = text; }
  function syncRecording() {
    values[6]=recording.format; values[20]=qsRecording.dcLabel(recording); values[4]=qsRecording.resLabel(recording);
  }
  function valueList() {
    if (customScope && dimensionField!=='preset') {
      if (dimensionField!=='ratio') return [];
      const ratio=recording[customScope].ratio;
      return qsRecording.ratios.includes(ratio) ? qsRecording.ratios : [...qsRecording.ratios,ratio];
    }
    if (selected===4) return qsRecording.resOptions(recording);
    if (selected===20) return recording.dc.preset==='自訂' ? [...qsRecording.dcOptions,qsRecording.dcLabel(recording)] : qsRecording.dcOptions;
    return items[selected][2];
  }
  function currentValue() { return customScope && dimensionField!=='preset' ? recording[customScope][dimensionField] : values[selected]; }
  function dimensionLimit() { return customScope==='res' && ['width','height'].includes(dimensionField) ? recording.dc[dimensionField] : qsRecording.limit; }
  function controlName() { return customScope ? dimensionField==='preset' ? customScope.toUpperCase() : `${customScope==='dc' ? 'DC' : 'RES'} ${dimensionField==='width' ? '寬度' : dimensionField==='height' ? '高度' : '比例'}` : items[selected][0]; }
  function enterDimensions() {
    if (dimensionTransition || customScope || editing || ![4,20].includes(selected)) return;
    const scope=selected===20 ? 'dc' : 'res';
    stop(true); cancelSettle(); lastTap=null; backgroundEditing=false;
    transitionDimensions(()=>{
      customScope=scope; dimensionField='width'; draw();
      say(`${scope.toUpperCase()} 自訂寬度、高度與比例`);
    });
  }
  function transitionDimensions(refresh,direction=1,fromY=0,fromOpacity=1) {
    cancelDimensionTransition();
    if (NO_ANIMATION || reducedMotion.matches) { refresh(); return; }
    const transition={animation:null}; dimensionTransition=transition;
    qsContent.inert=true; panel.setAttribute('aria-busy','true'); root.dataset.qsRefresh='out';
    transition.animation=qsContent.animate([{transform:`translateY(${fromY}px)`,opacity:fromOpacity},{transform:`translateY(${fromY+direction*18}px)`,opacity:0}],
      {duration:90,easing:'ease-in',fill:'forwards'});
    transition.animation.onfinish=()=>{
      if (dimensionTransition!==transition) return;
      refresh(); transition.animation.cancel(); root.dataset.qsRefresh='in';
      transition.animation=qsContent.animate([{transform:`translateY(${-direction*22}px)`,opacity:0},{transform:'translateY(0)',opacity:1}],
        {duration:140,easing:'cubic-bezier(.2,.75,.2,1)',fill:'forwards'});
      transition.animation.onfinish=()=>{ if (dimensionTransition===transition) cancelDimensionTransition(); };
    };
  }
  function cancelDimensionTransition() {
    const transition=dimensionTransition; dimensionTransition=null;
    transition?.animation?.cancel(); qsContent.inert=false; panel.removeAttribute('aria-busy'); root.dataset.qsRefresh='idle';
    qsContent.style.transform=''; qsContent.style.opacity='';
  }
  function leaveDimensions(animate=false,fromY=0,fromOpacity=1) {
    cancelDimensionTransition(); stop(true); lastTap=null;
    const refresh=()=>{ customScope=null; dimensionField='width'; lastAdjustKey=''; draw(); alignGrid(); say('已返回 QS'); };
    if (animate) transitionDimensions(refresh,-1,fromY,fromOpacity); else refresh();
  }
  function restoreUpContent(fromY,fromOpacity) {
    cancelDimensionTransition();
    if (NO_ANIMATION || reducedMotion.matches) return;
    const transition={animation:qsContent.animate([{transform:`translateY(${fromY}px)`,opacity:fromOpacity},{transform:'translateY(0)',opacity:1}],
      {duration:100,easing:'cubic-bezier(.2,.75,.2,1)',fill:'forwards'})};
    dimensionTransition=transition; qsContent.inert=true; root.dataset.qsRefresh='restore';
    transition.animation.onfinish=()=>{ if (dimensionTransition===transition) cancelDimensionTransition(); };
  }
  function setDimension(value,commit=true) {
    if (!customScope || !['width','height'].includes(dimensionField) || !Number.isInteger(value) || value<1) return false;
    recording=qsRecording.dimension(recording,customScope,dimensionField,Math.min(value,dimensionLimit())); syncRecording(); draw();
    if (value!==currentValue()) dimensionInput.value=currentValue();
    if (commit) persist(); return true;
  }
  function selectDimensionField(field) {
    if (!customScope || !['preset','width','height','ratio'].includes(field)) return;
    if (field!==dimensionField && document.activeElement===dimensionInput) dimensionInput.blur();
    dimensionField=field; backgroundEditing=false; lastAdjustKey=''; draw();
  }
  function renderDimensions() {
    dimensionGrid.hidden=!customScope; gridViewport.hidden=!!customScope;
    if (!customScope) return;
    const d=recording[customScope];
    for (const field of ['preset','width','height','ratio']) {
      const b=actions[`dimension-${field}`],label=field==='preset' ? customScope.toUpperCase() : field==='ratio' ? '比例' : `${customScope==='dc' ? '裁切' : '解析'}${field==='width' ? '寬度' : '高度'}`;
      const value=field==='preset' ? customScope==='dc' ? qsRecording.dcLabel(recording) : qsRecording.resLabel(recording) : d[field];
      b.querySelector('.label').textContent=label;
      b.querySelector('.value').textContent=field==='preset' && d.preset==='自訂' ? `CUSTOM\n(${d.ratio})` : value;
      b.querySelector('.subvalue').textContent=['width','height'].includes(field) ? customScope==='res' ? `≤ ${recording.dc[field]} px` : 'px' : '';
      b.classList.toggle('selected',dimensionField===field); b.setAttribute('aria-pressed',String(dimensionField===field));
      b.setAttribute('aria-label',`${label}，${value}${['width','height'].includes(field) ? ' 像素' : ''}`);
      b.classList.toggle('recording-value',field==='preset');
      b.classList.toggle('crop-custom',field==='preset' && d.preset==='自訂');
    }
  }
  function validOrder(order) {
    return Array.isArray(order) && order.length > 0 && order.length <= 24 && new Set(order).size === order.length &&
      order.every(n => Number.isInteger(n) && n >= 0 && n < items.length);
  }
  function restore(state) {
    const s = state?.privateContent || state;
    let order = [1,2,3,4,5].includes(s?.version) && validOrder(s.order) ? s.order : null;
    const names = state?.qsItems || state?.modelContent?.qsItems;
    if (!order && Array.isArray(names)) {
      const candidate = names.map(name => items.findIndex(item => item[0] === name));
      if (validOrder(candidate)) order = candidate;
    }
    if (!order) return;
    ids = [...order];
    if (![4,5].includes(s?.version) && !ids.includes(20)) ids.splice(ids.includes(6) ? ids.indexOf(6)+1 : ids.length,0,20);
    if (Array.isArray(s?.values)) values = items.map((item,id) => item[2].includes(s.values[id]) ? s.values[id] : item[1]);
    recording=qsRecording.restore(s?.recording,s?.values); syncRecording();
    page = Number.isInteger(s?.page) ? Math.max(0,Math.min(s.page,Math.ceil(ids.length/8)-1)) : 0;
    selected = ids.slice(page*8,page*8+8).includes(s?.selected) ? s.selected : ids[page*8];
    if (Number.isInteger(s?.backgroundAlpha4) && s.backgroundAlpha4>=0 && s.backgroundAlpha4<=15) backgroundAlpha4=s.backgroundAlpha4;
    else {
      const percent=state?.backgroundPercent ?? state?.modelContent?.backgroundPercent;
      if (Number.isFinite(percent) && percent>=0 && percent<=100) backgroundAlpha4=Math.round(percent/100*15);
    }
    applyBackground(); draw(); alignGrid();
  }
  function persist() {
    pendingPersist = {modelContent:{qsItems:ids.map(id=>items[id][0]),selectedItem:items[selected][0],backgroundPercent:Math.round(backgroundAlpha4/15*100),
      recording:{format:recording.format,dc:{...recording.dc},res:{...recording.res},fps:values[5]}},
      privateContent:{version:5,order:[...ids],values:[...values],recording:qsRecording.restore(recording),page,selected,backgroundAlpha4}};
    if (persistHandle != null) return;
    persistHandle=window.requestIdleCallback ? window.requestIdleCallback(flushPersist,{timeout:300}) : setTimeout(flushPersist,120);
  }
  function flushPersist() {
    persistHandle=null; if (!pendingPersist) return;
    const payload=pendingPersist; pendingPersist=null;
    window.openai?.setWidgetState?.(payload)?.catch?.(()=>{});
  }
  function snapshotMetrics() { root.dataset.qsMetrics=JSON.stringify(metrics); }
  function applyBackground() {
    const percent=Math.round(backgroundAlpha4/15*100);
    backdrop.hidden=backgroundAlpha4===0;
    backdrop.style.backgroundColor=backgroundAlpha4===0 ? '' : backgroundAlpha4===15 ? 'rgb(0, 0, 0)' : `rgba(0, 0, 0, ${backgroundAlpha4/15})`;
    backdrop.dataset.paint=backgroundAlpha4===0 ? 'off' : backgroundAlpha4===15 ? 'opaque' : 'blend';
    actions.background.textContent=backgroundAlpha4 ? `背景 ${percent}%` : '背景 關';
    opacityInput.value=backgroundAlpha4; opacityInput.setAttribute('aria-valuetext',`${percent}%`);
    opacityOutput.textContent=`${percent}%`;
  }
  function setBackground(alpha) {
    if (!Number.isInteger(alpha) || alpha<0 || alpha>15) return;
    backgroundAlpha4=alpha; applyBackground();
  }
  function present(amount,settle) {
    if (NO_ANIMATION) { amount=['open','edit','catalog'].includes(mode) ? 682 : 0; settle=false; }
    reveal = Math.max(0,Math.min(682,amount)); panel.classList.toggle('settle',!!settle);
    panel.style.visibility = 'visible'; panel.style.transform = `translate3d(0,${(reveal/682-1)*100}%,0)`;
    panel.inert = reveal === 0; edgeButton.disabled = reveal > 0;
    screen.classList.toggle('qs-open',reveal > 0);
  }
  function renderAdjust() {
    const list=valueList(),value=currentValue(),numeric=!!customScope && ['width','height'].includes(dimensionField);
    const key=`${selected}|${value}|${list.join(',')}|${customScope}|${dimensionField}|${editing}|${backgroundEditing}|${mode==='catalog'}`;
    if (key===lastAdjustKey) return; lastAdjustKey=key;
    const at=list.indexOf(value);
    adjustbar.hidden = mode === 'catalog';
    adjustbar.setAttribute('aria-label',backgroundEditing ? 'QS 背景調整' : `${controlName()}，同頁調整列`);
    editCaption.hidden = true;
    options.hidden = editing || backgroundEditing || numeric; backgroundControls.hidden=!backgroundEditing || editing;
    dimensionControls.hidden=!numeric || editing || backgroundEditing;
    actions['more-options'].hidden=editing || backgroundEditing || !!customScope || ![4,20].includes(selected);
    for (const action of ['decrease','increase']) {
      const b = actions[action]; b.hidden = editing || backgroundEditing;
      b.disabled = numeric ? action==='decrease' ? value<=1 : value>=dimensionLimit() : action === 'decrease' ? at <= 0 : at >= list.length-1;
    }
    if (editing || backgroundEditing) return;
    if (numeric) {
      if (document.activeElement!==dimensionInput) dimensionInput.value=value;
      dimensionInput.max=dimensionLimit(); dimensionRange.max=dimensionLimit();
      dimensionInput.setAttribute('aria-label',`${controlName()}像素`);
      dimensionRange.value=value; dimensionRange.setAttribute('aria-label',`拖曳調整${controlName()}`); return;
    }
    if (active?.kind!=='value') settleValues();
    optionButtons.forEach((b,n)=>{
      const value=list[at+n-2], outside=n===0 || n===4;
      b.classList.toggle('option-empty',value==null); b.inert=outside || value==null;
      b.setAttribute('aria-hidden',String(outside || value==null)); b.disabled=value==null;
      if (value==null) { delete b.dataset.value; b.textContent=''; return; }
      b.dataset.value = value; b.textContent = value; b.setAttribute('aria-pressed',String(value === currentValue()));
      b.setAttribute('aria-label',`${controlName()} ${value}`);
    });
  }
  function draw() {
    metrics.draws++; screen.classList.toggle('qs-edit',editing); screen.classList.toggle('qs-dimensions',!!customScope);
    const pages = Math.ceil(ids.length/8); page = Math.max(0,Math.min(page,pages-1));
    const mm=qsRecording.cropMm(recording);
    tiles.forEach((tile,id) => {
      const index=ids.indexOf(id), itemPage=Math.floor(index/8), local=index%8;
      const primary=index>=0 && itemPage===page;
      tile.hidden=index<0 || mode==='catalog';
      tile.inert=!primary; tile.setAttribute('aria-hidden',String(!primary));
      if (!tile.hidden) tile.style.transform=`translate3d(${local%4*100}%,${Math.floor(local/4)*100}%,0)`;
      const size=id===20 ? recording.dc : id===4 ? recording.res : null,custom=size?.preset==='自訂';
      const display = custom ? `CUSTOM\n(${size.ratio})` : values[id] === '關' ? 'OFF' : values[id] === '開' ? 'ON' : values[id];
      if (tileParts[id].value.textContent!==display) { tileParts[id].value.textContent=display; metrics.valueWrites++; }
      const sub=id===4 ? `${recording.res.width} × ${recording.res.height}` : id===20 ? `${mm.width} × ${mm.height} mm` : id===5 ? values[4] : '';
      if (tileParts[id].subvalue.textContent!==sub) tileParts[id].subvalue.textContent=sub;
      tile.setAttribute('aria-label',`${items[id][0]}，${values[id]}${editing ? '，可拖曳排序' : toggles.has(id) ? '，點按切換' : [4,20].includes(id) ? '，點按在下方調整，點兩下進入更多選項' : '，點按在下方調整'}`);
      tile.classList.toggle('editing',editing); tile.classList.toggle('dragging',active?.drag === id);
      tile.classList.toggle('selected',!editing && selected === id);
      tile.classList.toggle('recording-value',id===6 || (id===4 && recording.dc.preset==='HD'));
      tile.classList.toggle('crop-custom',custom);
    });
    gridPages.forEach((group,n)=>{
      group.hidden=n>=pages; group.setAttribute('aria-hidden',String(n!==page));
    });
    if (lastOrder !== ids.join(',')) { ids.forEach((id,n) => gridPages[Math.floor(n/8)].append(tiles[id])); lastOrder = ids.join(','); }
    title.textContent = customScope ? `QS · ${customScope.toUpperCase()}` : mode === 'catalog' ? '添加項目' : editing ? '編輯 QS' : 'QS';
    actions.add.hidden=mode==='catalog' || !!customScope;
    actions.back.hidden=mode!=='catalog' && !customScope;
    catalogViewport.hidden = mode !== 'catalog';
    if (mode==='catalog') renderCatalog();
    rowDivider.hidden = mode === 'catalog';
    actions.background.hidden=editing || mode==='catalog';
    actions.background.setAttribute('aria-pressed',String(backgroundEditing));
    const count = mode === 'catalog' ? Math.max(1,Math.ceil((items.length-ids.length)/6)) : pages;
    const view = mode === 'catalog' ? catalogPage : page;
    pageLabel.textContent = `${view+1} / ${count}`;
    for (const a of ['previous','next']) {
      const b = actions[a]; b.hidden = count <= 1 || !!customScope;
      b.disabled = a === 'previous' ? view === 0 : view === count-1;
    }
    root.querySelector('.pager').hidden=!!customScope;
    ghost.hidden = !active || active.drag == null; renderDimensions(); renderAdjust();
    trash.hidden=!editing || mode!=='edit'; trash.disabled=ids.length<=1;
    trash.classList.toggle('is-over',!!active?.overTrash); ghost.classList.toggle('trash-hover',!!active?.overTrash);
    trashLabel.textContent=ids.length<=1 ? '至少保留一項' : active?.overTrash ? '放開移除' : '垃圾桶';
    trash.setAttribute('aria-label',`從 QS 移除${items[active?.drag ?? selected][0]}`);
    actions.close.setAttribute('aria-label',customScope ? '上滑返回 QS' : '上滑收起 QS');
  }
  function beginEdit(id=selected) {
    if (editing) return; cancelSettle(); backgroundEditing=false; lastTap=null; selected=id; editing = true; mode = 'edit'; say('拖曳排序，拖到垃圾桶放開即可移除'); draw();
  }
  function endReorder() {
    cancelSettle(); editing=false; mode='open'; draw(); alignGrid();
  }
  function open() { mode = 'open'; present(682,true); draw(); alignGrid(); }
  function close() { cancelDimensionTransition(); cancelSettle(); editing=false; lastTap=null; customScope=null; mode = 'closed'; present(0,true); draw(); }
  function renderCatalog() {
    const available = items.map((_,id) => id).filter(id => !ids.includes(id)),key=available.join(',');
    if (key!==catalogKey || !catalog.children.length) {
      catalogKey=key; catalog.replaceChildren();
      for (let start=0;start<Math.max(1,available.length);start+=6) {
        const group=document.createElement('div'); group.className='catalog-page';
        available.slice(start,start+6).forEach(id=>{
          const b=document.createElement('button'); b.type='button'; b.className='cursor-interaction';
          b.dataset.addItem=id; b.textContent=`＋ ${items[id][0]}`; group.append(b);
        });
        if (!available.length) group.textContent='已添加所有可用項目';
        catalog.append(group);
      }
    }
    Array.from(catalog.children).forEach((group,n)=>{
      group.hidden=n!==catalogPage && !(!NO_ANIMATION && revealAdjacent && Math.abs(n-catalogPage)<=1);
      group.inert=n!==catalogPage; group.setAttribute('aria-hidden',String(n!==catalogPage));
      group.style.transform=`translate3d(${(n-catalogPage)*100}%,0,0)`;
    });
  }
  function showCatalog() { stop(true); cancelSettle(); editing=false; lastTap=null; backgroundEditing=false; mode = 'catalog'; catalogPage = 0; renderCatalog(); draw(); }
  function addItem(id) {
    if (ids.includes(id) || ids.length >= 24) return;
    cancelSettle();
    ids.push(id); page = Math.floor((ids.length-1)/8); selected = id; editing=false; mode = 'open'; persist(); say(`已添加${items[id][0]}`); draw(); alignGrid();
  }
  function removeItem(id) {
    const index=ids.indexOf(id);
    if (index<0 || ids.length<=1) return false;
    if (checkMotion) root.dataset.qsTrashRemoved=String(id);
    cancelSettle(); ids.splice(index,1); selected=ids[Math.min(index,ids.length-1)]; page=Math.floor(ids.indexOf(selected)/8);
    editing=false; mode='open'; lastTap=null; persist(); say(`已從 QS 移除${items[id][0]}`); return true;
  }
  function setValue(value,commit=true,announce=true) {
    if (!valueList().includes(value) || editing || value===currentValue()) return;
    const id=selected;
    if (customScope) recording=dimensionField==='preset' ? qsRecording.select(recording,customScope,value) : qsRecording.dimension(recording,customScope,'ratio',value);
    else if ([4,6,20].includes(id)) recording=qsRecording.select(recording,id===4 ? 'res' : id===6 ? 'format' : 'dc',value);
    else values[id]=value;
    syncRecording(); draw();
    if (!NO_ANIMATION) {
      tileParts[id].value.classList.add('changed'); clearTimeout(flashTimers.get(id));
      flashTimers.set(id,setTimeout(()=>tileParts[id].value.classList.remove('changed'),240));
    }
    if (announce) say(`${controlName()} ${value}`);
    if (commit) persist(); snapshotMetrics();
  }
  function activate(id) {
    if (editing) return; backgroundEditing=false; selected = id;
    if (toggles.has(id)) setValue(values[id] === '關' ? '開' : '關');
    else { say(`${items[id][0]}，在下方調整`); draw(); }
  }
  function pageView(surface) { return surface==='catalog' ? catalogPage : page; }
  function pageCount(surface) { return surface==='catalog' ? Math.max(1,Math.ceil((items.length-ids.length)/6)) : Math.ceil(ids.length/8); }
  function pageTarget(surface) { return surface==='catalog' ? catalog : gridViewport; }
  function alignGrid() {
    if (customScope) return;
    if (!gridWidth) gridWidth=gridViewport.clientWidth;
    gridViewport.scrollLeft=page*gridWidth;
  }
  function paintPage(surface,x,width) {
    if (NO_ANIMATION) { x=0; }
    if (surface==='catalog') catalog.style.transform=`translate3d(${x}px,0,0)`;
    else gridViewport.scrollLeft=page*width-x;
  }
  function updateNativeGridPage() {
    const width=gridWidth || gridViewport.clientWidth,next=Math.max(0,Math.min(pageCount('grid')-1,Math.round(gridViewport.scrollLeft/width)));
    if (Math.abs(gridViewport.scrollLeft-next*width)>1.5) return false;
    if (next!==page) {
      page=next; selected=ids[page*8]; draw(); persist(); say(`第 ${page+1} 頁，共 ${pageCount('grid')} 頁`);
      snapshotMetrics();
    }
    return true;
  }
  function finishNativeGrid() {
    clearTimeout(gridEndTimer); gridEndTimer=0;
    if (mode!=='open' || editing || active || pageMotion || (gridWheel && !gridWheel.committed) || !updateNativeGridPage()) return;
    gridScrolling=false;
    snapshotMetrics();
  }
  function queueGridEnd() { clearTimeout(gridEndTimer); gridEndTimer=setTimeout(finishNativeGrid,120); }
  function stopWheel() {
    if (wheelFrame) cancelAnimationFrame(wheelFrame);
    wheelFrame=0; gridWheel=null;
  }
  function releaseWheel(now) {
    wheelFrame=0;
    const wheel=gridWheel;
    if (!wheel || active || mode!=='open' || editing) return;
    // Check on the next frame, without waiting for scrollend or OS momentum to expire.
    if (now-wheel.lastMs<16) { wheelFrame=requestAnimationFrame(releaseWheel); return; }
    const offset=NO_ANIMATION ? wheel.offset : page*wheel.width-gridViewport.scrollLeft;
    const velocity=qsMotionVelocity(wheel.samples,wheel.eventMs);
    const to=qsPagerDestination(wheel.origin,offset,velocity,wheel.width,pageCount('grid'));
    wheel.snapping=true;
    settlePage('grid',to,offset,velocity,wheel.width,wheel.lastMs);
  }
  gridViewport.addEventListener('wheel',e=>{
    if (dimensionTransition) { if (e.cancelable) e.preventDefault(); return; }
    if (e.ctrlKey || mode!=='open' || editing || (!e.shiftKey && Math.abs(e.deltaX)<=Math.abs(e.deltaY))) return;
    if (!e.cancelable) return;
    e.preventDefault();
    if (active) stop(true);
    const width=gridWidth || gridViewport.clientWidth,now=performance.now();
    const delta=(e.deltaX || (e.shiftKey ? e.deltaY : 0))*(e.deltaMode===1 ? 16 : e.deltaMode===2 ? width : 1);
    if (!delta) return;
    metrics.wheelEvents++;
    const direction=Math.sign(delta),previous=gridWheel;
    const fresh=!previous || now-previous.lastMs>160 || (direction!==previous.direction && Math.abs(delta)>4);
    if (fresh) {
      stopWheel();
      gridWheel={origin:page,width,direction,lastMs:now,eventMs:e.timeStamp,samples:[],snapping:false,committed:false,logical:page*width,offset:0};
      qsMotionSample(gridWheel.samples,page*width-gridViewport.scrollLeft,e.timeStamp-16);
      if (checkMotion) motionTrace=[];
    }
    const wheel=gridWheel;
    wheel.lastMs=now; wheel.eventMs=e.timeStamp;
    // Do not let a decaying trackpad tail start another page or restart a completed snap.
    if (wheel.committed || (wheel.snapping && Math.abs(delta)<2)) return;
    if (pageMotion?.surface==='grid') cancelSettle(false);
    wheel.snapping=false;
    const min=Math.max(0,wheel.origin-1)*width,max=Math.min(pageCount('grid')-1,wheel.origin+1)*width;
    if (NO_ANIMATION) {
      wheel.logical=Math.max(min,Math.min(max,wheel.logical+delta)); wheel.offset=page*width-wheel.logical;
    } else gridViewport.scrollLeft=Math.max(min,Math.min(max,gridViewport.scrollLeft+delta));
    gridScrolling=true;
    qsMotionSample(wheel.samples,NO_ANIMATION ? wheel.offset : page*width-gridViewport.scrollLeft,e.timeStamp);
    if (checkMotion) traceMotion('wheel-input',{surface:'grid',origin:page,width,x:page*width-gridViewport.scrollLeft,velocity:qsMotionVelocity(wheel.samples),to:page});
    if (!wheelFrame) wheelFrame=requestAnimationFrame(releaseWheel);
  },{passive:false});
  gridViewport.addEventListener('scroll',()=>{
    if (mode!=='open' || editing) return;
    gridScrolling=true; metrics.scrollEvents++;
    if (!active && !pageMotion && !gridWheel) updateNativeGridPage();
    queueGridEnd();
  },{passive:true});
  gridViewport.addEventListener('scrollend',finishNativeGrid,{passive:true});
  function traceMotion(phase,state,offset=state.x) {
    if (!checkMotion) return;
    motionTrace.push({phase,surface:state.surface,x:(state.origin-pageView(state.surface))*state.width+offset,offset,
      velocity:state.velocity,page:pageView(state.surface),to:state.to,ms:performance.now(),inline:pageTarget(state.surface).style.transform,
      scrollLeft:state.surface==='grid' ? gridViewport.scrollLeft : undefined});
    if (motionTrace.length>160) motionTrace.shift();
  }
  function cancelSettle(reset=true) {
    const old=pageMotion;
    if (pageFrame) cancelAnimationFrame(pageFrame); pageFrame=0; pageMotion=null;
    if (old) traceMotion('interrupt',old);
    if (reset) {
      stopWheel();
      revealAdjacent=false; catalog.style.transform=''; gridViewport.style.scrollSnapType='';
      clearTimeout(gridEndTimer); gridEndTimer=0; gridScrolling=false; alignGrid();
    }
    return old;
  }
  function finishPageMotion(state) {
    pageMotion=null; pageFrame=0;
    const changed=pageView(state.surface)!==state.to;
    if (state.surface==='catalog') catalogPage=state.to;
    else { page=state.to; if (changed) selected=ids[page*8]; }
    revealAdjacent=false; paintPage(state.surface,0,state.width);
    if (state.surface==='grid') {
      gridViewport.style.scrollSnapType=''; gridScrolling=false;
      if (gridWheel?.snapping) gridWheel.committed=true;
    }
    draw(); traceMotion('commit',state,0);
    if (changed) { say(`第 ${state.to+1} 頁，共 ${pageCount(state.surface)} 頁`); if (!editing) persist(); }
    snapshotMetrics();
    if (checkMotion) root.dataset.qsMotionTrace=JSON.stringify(motionTrace);
  }
  function settlePage(surface,to,x,velocity,width,startMs=performance.now()) {
    cancelSettle(false);
    const origin=pageView(surface),target=(origin-to)*width;
    const state=Object.assign(surface==='grid' ? qsPagerStart(x,velocity,target,width) : qsMotionStart(x,velocity,target),
      {surface,origin,to,width,lastMs:startMs});
    pageMotion=state; revealAdjacent=true;
    if (surface==='grid') gridViewport.style.scrollSnapType='none';
    paintPage(surface,x,width);
    traceMotion('release',state);
    if (NO_ANIMATION || state.done || reducedMotion.matches) { state.x=state.target; finishPageMotion(state); return; }
    function frame(now) {
      if (pageMotion!==state) return;
      (surface==='grid' ? qsPagerStep : qsMotionStep)(state,now-state.lastMs); state.lastMs=now;
      paintPage(surface,state.x,width); traceMotion('frame',state);
      if (state.done) finishPageMotion(state);
      else pageFrame=requestAnimationFrame(frame);
    }
    // Consume any elapsed wheel hand-off time on the first frame.
    if (surface==='grid' && performance.now()-startMs>=1) frame(performance.now());
    else pageFrame=requestAnimationFrame(frame);
  }
  function valueTransform(offset) { return `translate3d(calc(-33.333333% + ${offset}px),0,0)`; }
  function settleValues(offset=0) {
    if (valueAnimation) { valueAnimation.cancel(); valueAnimation=null; }
    optionTrack.style.transform='';
    if (NO_ANIMATION || reducedMotion.matches || Math.abs(offset)<0.5) return;
    const animation=optionTrack.animate([{transform:valueTransform(offset)},{transform:valueTransform(0)}],
      {duration:110,easing:'cubic-bezier(.2,.75,.2,1)'});
    valueAnimation=animation;
    animation.onfinish=()=>{ if (valueAnimation===animation) valueAnimation=null; };
  }
  function changePage(delta) {
    if (customScope || dimensionTransition) return false;
    if (!['open','edit','catalog'].includes(mode)) return false;
    if (active?.kind==='value') return false;
    const limit = mode === 'catalog' ? Math.max(1,Math.ceil((items.length-ids.length)/6)) : Math.ceil(ids.length/8);
    const old = mode === 'catalog' ? catalogPage : page, next = old+delta;
    if (next < 0 || next >= limit) return false;
    cancelSettle();
    if (mode === 'catalog') { catalogPage = next; renderCatalog(); }
    else { page = next; if (active?.drag == null) selected = ids[page*8]; }
    draw(); if (mode!=='catalog') alignGrid(); say(`第 ${next+1} 頁，共 ${limit} 頁`);
    if (!editing) persist();
    return true;
  }
  function point(e,r) { return {x:(e.clientX-r.left)/r.width*1024,y:(e.clientY-r.top)/r.height*682,ms:e.timeStamp}; }
  function local(e) { return point(e,active.bounds); }
  function slot(x,y) {
    if (x < 0 || x >= 1024 || y < 110 || y >= 534) return -1;
    const i=page*8+Math.floor((y-110)/212)*4+Math.floor(x/256); return i < ids.length ? i : -1;
  }
  function moveGhost(x,y) { ghost.style.transform=`translate3d(${x/1024*active.bounds.width}px,${y/682*active.bounds.height}px,0) translate(-50%,-50%)`; }
  function overTrash(x,y) {
    if (ids.length<=1) return false;
    if (!active.trashBounds) {
      const r=trash.getBoundingClientRect(),b=active.bounds; metrics.boundsReads++;
      active.trashBounds={left:(r.left-b.left)/b.width*1024,right:(r.right-b.left)/b.width*1024,
        top:(r.top-b.top)/b.height*682,bottom:(r.bottom-b.top)/b.height*682};
    }
    const r=active.trashBounds;
    return x>=r.left && x<=r.right && y>=r.top && y<=r.bottom;
  }
  function cancelMove() { if (moveFrame) cancelAnimationFrame(moveFrame); moveFrame=0; pendingPoint=null; }
  function stop(cancel) {
    cancelMove();
    clearTimeout(timer); clearTimeout(edgeTimer); timer=edgeTimer=0;
    const hadMotion=!!pageMotion;
    if (cancel) cancelSettle();
    if (!active) { if (cancel && hadMotion) draw(); return; }
    if (!pageMotion) catalog.style.transform='';
    if (cancel) {
      lastTap=null;
      ids=active.order; page=active.page; selected=active.selectedStart;
      if (active.kind === 'edge') { mode='closed'; present(0,true); }
      else present(682,true);
      if (active.kind==='up' && active.upBack) restoreUpContent(active.upY,active.upOpacity);
    }
    if (active.kind==='value') {
      if (cancel) {
        if (customScope || [4,6,20].includes(selected)) { recording=qsRecording.restore(active.recordingStart); syncRecording(); draw(); }
        else setValue(active.valueStart,false,false);
      }
      settleValues(cancel ? 0 : active.valueOffset);
      if (!cancel && currentValue()!==active.valueStart) persist();
      say(`${controlName()} ${currentValue()}`);
    }
    const reordered=editing;
    if (reordered) {
      editing=false; mode='open';
      if (!cancel && active.id!=null) {
        if (!(active.drag!=null && active.overTrash && removeItem(active.id))) {
          selected=active.id; page=Math.floor(ids.indexOf(selected)/8);
          if (ids.join(',')!==active.order.join(',')) { persist(); say('QS 位置已儲存'); }
        }
      }
    }
    const wasPage=active.kind==='page';
    if (active.id!=null) tiles[active.id].classList.remove('pressed'); active=null;
    if (wasPage && !cancel) { ghost.hidden=true; if (pageMotion) traceMotion('contact-end',pageMotion); snapshotMetrics(); return; }
    draw(); if (cancel || reordered) alignGrid();
    if (gridScrolling && !pageMotion) finishNativeGrid();
    snapshotMetrics();
  }
  screen.addEventListener('pointerdown',e=>{
    if (dimensionTransition) { e.preventDefault(); return; }
    if (suppressed.size) { suppressed.add(e.pointerId); e.preventDefault(); return; }
    if (active) { suppressed.add(active.pointer); suppressed.add(e.pointerId); stop(true); e.preventDefault(); return; }
    const b=e.target.closest('button'), onValues=!!e.target.closest('.inline-options'),onDimension=!!e.target.closest('.dimension-grid');
    if (b?.dataset.item==null || Number(b.dataset.item)!==lastTap?.id || editing) lastTap=null;
    if ((e.target.closest('.adjustbar') && !onValues) || (b?.dataset.action && b.dataset.action !== 'close' && !onDimension)) return;
    if (onValues && (mode!=='open' || editing || backgroundEditing)) return;
    metrics.boundsReads++; const bounds=screen.getBoundingClientRect(),p=point(e,bounds);
    stopWheel();
    let carry=null;
    const nativeOffset=page*(gridWidth || bounds.width)-gridViewport.scrollLeft;
    if (pageMotion) {
      if (onValues) {
        const previous=cancelSettle(false);
        settlePage(previous.surface,previous.origin,previous.x,previous.velocity,previous.width);
      } else if ((mode==='catalog' || (p.y>=110 && p.y<534))) carry=cancelSettle(false);
      else { cancelSettle(); draw(); }
    }
    if (!pageMotion && !carry && mode==='open' && Math.abs(nativeOffset)>1) {
      if (onValues) settlePage('grid',page,nativeOffset,0,gridWidth || bounds.width);
      else if (p.y>=110 && p.y<534) {
        carry={x:nativeOffset}; gridScrolling=false; gridViewport.style.scrollSnapType='none';
      }
    }
    let kind=null, id=b?.dataset.item;
    if (onValues) kind='value';
    else if (customScope && onDimension) kind='dimension';
    else if (carry) kind='page';
    else if (mode === 'closed' && p.y <= 32) kind='edge';
    else if (mode === 'catalog') kind='catalog';
    else if (mode === 'open' || mode === 'edit') kind=id != null ? 'item' : p.y < 100 || p.y >= 658 ? 'handle' : 'blocked';
    if (!kind) return;
    e.preventDefault(); screen.setPointerCapture(e.pointerId);
    active={pointer:e.pointerId,x0:p.x,y0:p.y,x:p.x,y:p.y,kind,id:id == null ? null:Number(id),
      add:b?.dataset.addItem == null ? null:Number(b.dataset.addItem),moved:!!carry,pressCleared:false,drag:null,order:[...ids],page,selectedStart:selected,bounds,
      surface:mode==='catalog' ? 'catalog' : 'grid',pageBase:carry?.x || 0,carried:!!carry,pageSamples:[]};
    active.dimensionField=onDimension ? b?.dataset.action?.slice(10) : null;
    active.pageWidth=active.surface==='catalog' ? catalogViewport.getBoundingClientRect().width : (gridWidth || bounds.width);
    if (active.surface==='catalog') metrics.boundsReads++;
    const offset=carry?.x || 0,view=pageView(active.surface);
    const min=view<pageCount(active.surface)-1 ? -active.pageWidth : 0,max=view>0 ? active.pageWidth : 0;
    active.pageBase=active.surface==='grid' ? offset : offset<min ? min+(offset-min)*4 : offset>max ? max+(offset-max)*4 : offset;
    qsMotionSample(active.pageSamples,offset,p.ms); pageDragPx=offset;
    if (checkMotion && !carry) motionTrace=[];
    if (kind==='value') {
      settleValues(); metrics.boundsReads++;
      Object.assign(active,{valueStart:currentValue(),valueIndex:valueList().indexOf(currentValue()),recordingStart:qsRecording.restore(recording),
        valueTap:b?.dataset.value,valuePitch:options.getBoundingClientRect().width/3,valueOffset:0,valueLocked:false});
    }
    if (kind === 'item') {
      tiles[active.id].classList.add('pressed');
      if (!editing) timer=setTimeout(()=>{
        if (!active || active.moved) return; beginEdit(active.id); active.drag=active.id;
        ghost.replaceChildren(...Array.from(tiles[active.id].children).map(n=>n.cloneNode(true))); moveGhost(active.x,active.y); draw();
      },480);
    }
  });
  function motion(p) {
    const dx=p.x-active.x0,dy=p.y-active.y0; active.x=p.x; active.y=p.y;
    if (dx*dx+dy*dy > 144) {
      active.moved=true; lastTap=null; clearTimeout(timer);
      if (!active.pressCleared) { if (active.id!=null) tiles[active.id].classList.remove('pressed'); active.pressCleared=true; }
    }
    const px=dx/1024*active.bounds.width,py=dy/682*active.bounds.height;
    if (!editing && mode==='open' && !active.valueLocked && ['item','blocked','handle','dimension','value'].includes(active.kind) &&
      py < -8 && -py>Math.abs(px)*1.25) {
      active.kind='up'; active.moved=true; active.upBack=!!customScope; lastTap=null; clearTimeout(timer); cancelSettle();
      if (active.id!=null) tiles[active.id].classList.remove('pressed');
      active.pressCleared=true;
    }
    if (!customScope && !editing && mode === 'open' && active.y0 >= 110 && active.y0 < 534 &&
      ['item','blocked'].includes(active.kind) && Math.abs(dx)/1024*active.bounds.width>4 && Math.abs(dx)>Math.abs(dy)*1.2) {
      active.kind='page'; active.moved=true; clearTimeout(timer);
      if (active.id!=null) tiles[active.id].classList.remove('pressed');
      active.pressCleared=true; gridViewport.style.scrollSnapType='none';
    }
    if (active.kind==='catalog' && Math.abs(dx)>18 && Math.abs(dx)*2>Math.abs(dy)*3) {
      active.kind='page'; revealAdjacent=true; renderCatalog();
    }
    if (active.kind==='up') {
      active.upY=Math.min(0,py); active.upOpacity=Math.max(0.15,1+active.upY/active.bounds.height);
      if (active.upBack) { if (!NO_ANIMATION) { qsContent.style.transform=`translate3d(0,${active.upY}px,0)`; qsContent.style.opacity=active.upOpacity; } }
      else present(682+Math.min(0,dy),false);
    } else if (active.kind === 'value') {
      if (!active.valueLocked && Math.abs(dx)>12 && Math.abs(dx)*2>Math.abs(dy)*3) active.valueLocked=true;
      if (active.valueLocked) {
        const list=valueList(),pitch=active.valuePitch,px=dx/1024*active.bounds.width;
        const next=Math.max(0,Math.min(list.length-1,Math.round(active.valueIndex-px/pitch)));
        setValue(list[next],false,false);
        let offset=px+(next-active.valueIndex)*pitch;
        if (next===0 && offset>0) offset=Math.min(pitch/4,offset/4);
        if (next===list.length-1 && offset<0) offset=Math.max(-pitch/4,offset/4);
        active.valueOffset=offset; optionTrack.style.transform=NO_ANIMATION ? '' : valueTransform(offset);
      }
    } else if (active.kind === 'edge') {
      if (mode === 'closed' && Math.abs(dx)>12 && Math.abs(dx)>Math.abs(dy)) active.kind='blocked';
      else if (dy>12 && dy>Math.abs(dx)) mode='pulling';
      if (mode === 'pulling') present(dy,false);
    } else if (active.kind === 'page') {
      const view=pageView(active.surface),raw=active.pageBase+dx/1024*active.bounds.width;
      const min=view<pageCount(active.surface)-1 ? -active.pageWidth : 0,max=view>0 ? active.pageWidth : 0;
      pageDragPx=active.surface==='grid' ? Math.max(min,Math.min(max,raw)) : raw<min ? min+(raw-min)*0.25 : raw>max ? max+(raw-max)*0.25 : raw;
      if (active.pageSamples[active.pageSamples.length-1]?.x!==pageDragPx) qsMotionSample(active.pageSamples,pageDragPx,p.ms);
      paintPage(active.surface,pageDragPx,active.pageWidth);
    } else if (active.kind === 'item' && editing && active.moved) {
      let needsDraw=false;
      if (active.drag == null) { active.drag=active.id; needsDraw=true; ghost.replaceChildren(...Array.from(tiles[active.id].children).map(n=>n.cloneNode(true))); }
      moveGhost(p.x,p.y); const hit=overTrash(p.x,p.y);
      if (hit!==!!active.overTrash) {
        active.overTrash=hit; needsDraw=true; if(hit) say('放開即可從 QS 移除');
        if (checkMotion) root.dataset.qsTrashHover=JSON.stringify({id:active.id,over:hit,x:p.x,y:p.y,bounds:active.trashBounds});
      }
      const at=hit ? -1 : slot(p.x,p.y),from=ids.indexOf(active.id);
      if (at >= 0 && from !== at) { ids.splice(from,1); ids.splice(at,0,active.id); needsDraw=true; }
      if (hit || p.y<110 || p.y>=534 || (p.x>=24 && p.x<=1000)) { clearTimeout(edgeTimer); edgeTimer=0; }
      else if (!edgeTimer) edgeTimer=setTimeout(()=>{
        edgeTimer=0; if (!active || active.overTrash || active.y<110 || active.y>=534 || (active.x>=24 && active.x<=1000)) return;
        changePage(active.x<24 ? -1 : 1,false);
      },550);
      if (needsDraw) draw();
    }
  }
  screen.addEventListener('pointermove',e=>{
    if (active?.pointer!==e.pointerId) return;
    const p=local(e),dx=p.x-active.x0,dy=p.y-active.y0;
    if (dx*dx+dy*dy>144) { active.moved=true; clearTimeout(timer); }
    if (mode==='open' && active.surface==='grid' && ['item','blocked','page','dimension','up'].includes(active.kind)) {
      metrics.pointerUpdates++; motion(p); return;
    }
    pendingPoint=p;
    if (!moveFrame) moveFrame=requestAnimationFrame(()=>{
      moveFrame=0; const latest=pendingPoint; pendingPoint=null;
      if (active && latest) { metrics.pointerUpdates++; motion(latest); }
    });
  });
  screen.addEventListener('pointerup',e=>{
    if (suppressed.has(e.pointerId)) { suppressed.delete(e.pointerId); return; }
    if (!active || e.pointerId !== active.pointer) return;
    cancelMove(); motion(local(e)); const a=active,dx=a.x-a.x0,dy=a.y-a.y0;
    if (a.kind==='up') {
      const commit=-a.upY>=Math.min(72,Math.max(36,a.bounds.height*0.14));
      stop(false);
      if (commit) { if (a.upBack) leaveDimensions(true,a.upY,a.upOpacity); else close(); }
      else if (a.upBack) restoreUpContent(a.upY,a.upOpacity);
      else present(682,true);
      return;
    }
    let more=false;
    if (a.kind === 'value') { if (!a.moved && a.valueTap!=null) setValue(a.valueTap,false,false); }
    else if (a.kind === 'edge') { if ((NO_ANIMATION ? dy : reveal)>=180) open(); else { mode='closed'; present(0,true); } }
    else if (a.kind === 'handle') present(682,true);
    else if (a.kind==='dimension') {
      if (!a.moved && a.dimensionField) selectDimensionField(a.dimensionField);
    }
    else if (a.kind === 'page') {
      const view=pageView(a.surface),velocity=qsMotionVelocity(a.pageSamples,e.timeStamp);
      let destination;
      if (a.surface==='grid') destination=qsPagerDestination(view,pageDragPx,velocity,a.pageWidth,pageCount('grid'));
      else {
        const direction=pageDragPx<0 ? 1 : -1;
        const requested=Math.abs(pageDragPx)>=a.bounds.width*80/1024 && (a.carried || Math.abs(dx)>Math.abs(dy)) ? view+direction : view;
        destination=Math.max(0,Math.min(pageCount(a.surface)-1,requested));
      }
      settlePage(a.surface,destination,pageDragPx,velocity,a.pageWidth);
    } else if (a.kind === 'catalog') {
      if (!a.moved && a.add!=null) addItem(a.add);
    } else if (a.kind === 'item' && !editing && !a.moved && slot(a.x,a.y) === ids.indexOf(a.id)) {
      const x=e.clientX,y=e.clientY;
      more=[4,20].includes(a.id) && lastTap?.id===a.id && lastTap.type===e.pointerType &&
        e.timeStamp-lastTap.ms<=350 && Math.hypot(x-lastTap.x,y-lastTap.y)<=24;
      lastTap=more || ![4,20].includes(a.id) ? null : {id:a.id,ms:e.timeStamp,x,y,type:e.pointerType};
      activate(a.id);
    } else lastTap=null;
    stop(false);
    if (more) enterDimensions();
  });
  screen.addEventListener('pointercancel',e=>{ suppressed.delete(e.pointerId); if (active?.pointer === e.pointerId) stop(true); });
  screen.addEventListener('lostpointercapture',e=>{ if (active?.pointer === e.pointerId) stop(true); });
  root.addEventListener('click',e=>{
    const b=e.target.closest('button'); if (!b || b.disabled) return;
    if (b.dataset.addItem != null) { if (e.detail === 0) addItem(Number(b.dataset.addItem)); }
    else if (b.dataset.value != null) { if (e.detail===0) setValue(b.dataset.value); }
    else if (b.dataset.action) {
      const a=b.dataset.action;
      if (a === 'qs') { stop(true); if (customScope) leaveDimensions(); else mode === 'closed' ? open() : close(); }
      else if (a === 'background') { backgroundEditing=!backgroundEditing; draw(); }
      else if (a === 'background-off') { setBackground(0); persist(); say('QS 背景已關閉'); snapshotMetrics(); }
      else if (a === 'add') showCatalog();
      else if (a === 'trash' && editing && !active) { if (removeItem(selected)) { draw(); alignGrid(); tiles[selected].focus(); } }
      else if (a === 'more-options') enterDimensions();
      else if (a.startsWith('dimension-')) {
        selectDimensionField(a.slice(10));
      }
      else if (a === 'back') { if (customScope) leaveDimensions(); else { cancelSettle(); mode='open'; draw(); } }
      else if (a === 'previous' || a === 'next') changePage(a === 'next' ? 1 : -1);
      else if (a === 'increase' || a === 'decrease') {
        if (customScope && ['width','height'].includes(dimensionField)) setDimension(currentValue()+(a==='increase' ? 1 : -1));
        else {
          const list=valueList(),at=list.indexOf(currentValue())+(a === 'increase' ? 1 : -1);
          if (at>=0 && at<list.length) setValue(list[at]);
        }
      } else if (a === 'close' && e.detail === 0) { if (customScope) leaveDimensions(true); else close(); }
    } else if (e.detail === 0 && b.dataset.item != null) activate(Number(b.dataset.item));
    else if (b.classList.contains('edge') && e.detail === 0) open();
  });
  opacityInput.addEventListener('input',()=>setBackground(Number(opacityInput.value)));
  opacityInput.addEventListener('change',()=>{ persist(); say(`QS 背景 ${Math.round(backgroundAlpha4/15*100)}%`); snapshotMetrics(); });
  dimensionInput.addEventListener('input',()=>setDimension(dimensionInput.valueAsNumber));
  dimensionInput.addEventListener('change',()=>{
    if (!setDimension(dimensionInput.valueAsNumber)) dimensionInput.value=currentValue();
    say(`${controlName()} ${currentValue()} 像素`);
  });
  dimensionRange.addEventListener('input',()=>setDimension(Number(dimensionRange.value),false));
  dimensionRange.addEventListener('change',()=>{ persist(); say(`${controlName()} ${currentValue()} 像素`); });
  window.addEventListener('pagehide',flushPersist);
  window.addEventListener('keydown',e=>{
    if (e.key==='Escape' && dimensionTransition) {
      e.preventDefault(); e.stopPropagation();
      if (customScope) leaveDimensions(); else close();
    }
  },true);
  new ResizeObserver(()=>{
    gridWidth=gridViewport.clientWidth;
    if (active) stop(true); else if (pageMotion) { cancelSettle(); draw(); }
    alignGrid();
  }).observe(screen);
  root.addEventListener('keydown',e=>{
    if (dimensionTransition && e.key!=='Escape') { e.preventDefault(); return; }
    const b=e.target.closest('[data-item]');
    if (e.target.closest('.inline-options') && !active && !editing && ['ArrowLeft','ArrowRight'].includes(e.key)) {
      e.preventDefault(); const list=valueList(),at=list.indexOf(currentValue())+(e.key==='ArrowRight' ? 1 : -1);
      if (at>=0 && at<list.length) setValue(list[at]);
    }
    if (e.key === 'Escape') { stop(true); lastTap=null; if (customScope) leaveDimensions(); else if (mode === 'catalog') { mode='open'; draw(); } else if (editing) endReorder(); else close(); }
    if (e.key === 'PageDown' || e.key === 'PageUp') { e.preventDefault(); changePage(e.key === 'PageDown' ? 1 : -1); }
    if (b && e.key.toLowerCase() === 'e') { beginEdit(Number(b.dataset.item)); e.preventDefault(); }
    if (b && editing && !active && ['Delete','Backspace'].includes(e.key)) {
      e.preventDefault(); if (removeItem(Number(b.dataset.item))) { draw(); alignGrid(); tiles[selected].focus(); }
    }
    if (b && editing && !active && ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {
      e.preventDefault(); const from=ids.indexOf(Number(b.dataset.item));
      const to=from+({ArrowLeft:-1,ArrowRight:1,ArrowUp:-4,ArrowDown:4}[e.key]);
      if (to>=0 && to<ids.length) { const id=ids.splice(from,1)[0]; ids.splice(to,0,id); selected=id; page=Math.floor(to/8); persist(); draw(); alignGrid(); b.focus(); say(`${items[id][0]}，位置 ${to+1}，已儲存`); }
    }
  });
  window.addEventListener('openai:set_globals',e=>{ if (!active && !editing && !pageMotion && !gridScrolling && !customScope && !dimensionTransition) restore(e.detail?.globals?.widgetState); });
  syncRecording(); restore(window.openai?.widgetState); applyBackground(); draw(); alignGrid(); present(0,false); snapshotMetrics();
})();
