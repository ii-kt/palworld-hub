function openPicker(cb){
 if(!pals.length){toast(document.body.dataset.dataState==="error"?"データ検証に失敗しているため選択できません":"データを読み込んでいます");return}
 pickerCallback=cb;$("#pickerSearch").value="";$("#pickerModal").classList.add("open");renderPicker();setTimeout(()=>$("#pickerSearch").focus(),30);
}
function closePicker(){$("#pickerModal").classList.remove("open");pickerCallback=null}
function pickerFiltered(){
 const q=$("#pickerSearch").value||"",v=$("#pickerVariant").value,el=$("#pickerElement").value,w=$("#pickerWork").value,l=+$("#pickerLevel").value,s=$("#pickerSort").value;
 let list=pals.filter(p=>searchable(p,q)&&(v==="all"||(v==="variant")===p.variant)&&(!el||p.elements.includes(el))&&matchesWorkFilter(p,w,l));
 list.sort((a,b)=>s==="desc"?palSort(b,a):s==="jp"?a.jp.localeCompare(b.jp,"ja"):palSort(a,b));return list;
}
function renderPicker(){
 const list=pickerFiltered();
 $("#pickerList").innerHTML=list.map(p=>`<button class="picker-item" data-id="${esc(p.uid)}">${mark(p,true)}<span style="min-width:0"><strong>${esc(p.jp)}</strong><small class="enname">${esc(p.en)} · No.${esc(displayNo(p))} · 配合値${p.power}</small><small class="form-id">形態ID ${esc(formId(p))}</small></span></button>`).join("");
}
function toast(msg){const t=$("#toast");t.textContent=msg;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),1800)}
function renderTree(){
 const canvas=$("#treeCanvas");if(!selected.tree){canvas.innerHTML=`<div class="empty" style="width:420px">起点パルを選択してください</div>`;return}
 const depth=+$("#treeDepth").value;
 canvas.innerHTML=treeOrientation==="result"?ancestorNode(selected.tree,0,depth,"r","",new Set()):descendantNode(selected.tree,0,depth,"d",new Set());
 applyTreeTransform();
}
function isGenderSpecific(result){return result&&(result.parent1Gender!=="WILDCARD"||result.parent2Gender!=="WILDCARD")}
function requiredGenderFor(result,pal){
 if(!result)return "";
 if(pal.uid===result.first.uid)return genderMark(result.parent1Gender);
 if(pal.uid===result.second.uid)return genderMark(result.parent2Gender);
 return "";
}
function orderedAncestorPairs(p){
 return [...(parentsByChild.get(p.uid)||[])].sort((a,b)=>{
  const aCycles=Number(a.first.uid===p.uid||a.second.uid===p.uid);
  const bCycles=Number(b.first.uid===p.uid||b.second.uid===p.uid);
  return aCycles-bCycles||palSort(a.first,b.first)||palSort(a.second,b.second);
 });
}
function orderedDescendantPairs(p){
 return (offspringByParent.get(p.uid)||[]).flatMap(group=>group.results.map(result=>({...result,partner:group.partner}))).sort((a,b)=>Number(a.child.uid===p.uid)-Number(b.child.uid===p.uid)||palSort(a.child,b.child)||palSort(a.partner,b.partner));
}
function nodeCard(p,pairs,path,requiredGender="",condition=""){
 const idx=Math.min(treeSelections.get(path)||0,Math.max(0,pairs.length-1));treeSelections.set(path,idx);
 return `<div class="tree-node">${palHTML(p,true)}<div class="no" style="text-align:center;margin-top:4px">配合値 ${p.power}</div>${requiredGender?`<div class="tree-gender">必要性別 ${esc(requiredGender)}</div>`:""}${condition?`<div class="tree-condition">${esc(condition)}</div>`:""}${pairs.length?`<div class="combo-nav"><button data-nav="${path}" data-d="-1">‹</button><span>${idx+1} / ${pairs.length}</span><button data-nav="${path}" data-d="1">›</button></div>`:""}</div>`;
}
function ancestorNode(p,level,max,path,requiredGender="",ancestors=new Set()){
 if(ancestors.has(p.uid))return `<div class="tree-branch">${nodeCard(p,[],path,requiredGender,"循環配合のため、ここで展開を停止")}</div>`;
 const nextAncestors=new Set(ancestors);nextAncestors.add(p.uid);
 const pairs=orderedAncestorPairs(p),idx=Math.min(treeSelections.get(path)||0,Math.max(0,pairs.length-1)),r=pairs[idx];
 const condition=isGenderSpecific(r)?r.note:"";
 if(level>=max||!r)return `<div class="tree-branch">${nodeCard(p,pairs,path,requiredGender)}</div>`;
 return `<div class="tree-branch">${nodeCard(p,pairs,path,requiredGender,condition)}<div class="tree-edge"></div><div class="tree-children">${ancestorNode(r.first,level+1,max,path+"a",requiredGenderFor(r,r.first),nextAncestors)}${ancestorNode(r.second,level+1,max,path+"b",requiredGenderFor(r,r.second),nextAncestors)}</div></div>`;
}
function descendantNode(p,level,max,path,ancestors=new Set()){
 if(ancestors.has(p.uid))return `<div class="tree-branch">${nodeCard(p,[],path,"","循環配合のため、ここで展開を停止")}</div>`;
 const nextAncestors=new Set(ancestors);nextAncestors.add(p.uid);
 const pairs=orderedDescendantPairs(p),idx=Math.min(treeSelections.get(path)||0,Math.max(0,pairs.length-1)),r=pairs[idx];
 const condition=isGenderSpecific(r)?r.note:"";
 const parentGender=requiredGenderFor(r,p);
 if(level>=max||!r)return `<div class="tree-branch">${nodeCard(p,pairs,path)}</div>`;
 return `<div class="tree-branch">${nodeCard(p,pairs,path,parentGender,condition)}<div class="tree-edge"></div><div class="tree-children"><div class="tree-branch">${nodeCard(r.partner,[],path+"p",requiredGenderFor(r,r.partner))}</div>${descendantNode(r.child,level+1,max,path+"c",nextAncestors)}</div></div>`;
}
function applyTreeTransform(){$("#treeCanvas").style.transform=`translate(${panX}px,${panY}px) scale(${zoom})`}
function renderAll(){renderParents();renderTarget();renderOffspring();renderDex();renderTree()}

$("#treeCanvas").addEventListener("pointerdown",event=>{
 if(event.target.closest("[data-nav]"))event.stopPropagation();
});
