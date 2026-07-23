const HOWTO_BY_TAB={
 parents:["「親Aを選択」を押す","「親Bを選択」を押す","子パルが表示される（性別依存は条件別）"],
 target:["「作りたいパルを選択」を押す","子パルを検索して選ぶ","作れる親の組合せが一覧表示される"],
 offspring:["「基準にする親」を押す","親パルを検索して選ぶ","相手パルと子パルの全候補が表示される"],
 tree:["「起点パルを選択」を押す","起点パルと表示世代数を選ぶ","系譜を移動・拡大して確認する"],
 dex:["名前・図鑑番号を入力する","属性・作業適性などで絞り込む","一覧からパル情報を確認する"]
};
function updateHowto(tab){
 const steps=HOWTO_BY_TAB[tab]||HOWTO_BY_TAB.parents;
 document.querySelectorAll(".howto span").forEach((el,i)=>{el.textContent=steps[i]||""});
}

$("#tabs").addEventListener("click",e=>{
 const b=e.target.closest("button[data-tab]");if(!b)return;
 document.querySelectorAll(".tabs button").forEach(x=>x.classList.toggle("active",x===b));
 document.querySelectorAll(".view").forEach(v=>v.hidden=v.id!=="view-"+b.dataset.tab);
 updateHowto(b.dataset.tab);
 if(b.dataset.tab==="tree")renderTree();
});
$("#parentA").onclick=()=>openPicker(p=>{selected.a=p;renderParents()});
$("#parentB").onclick=()=>openPicker(p=>{selected.b=p;renderParents()});
$("#targetPick").onclick=()=>openPicker(p=>{selected.target=p;renderTarget()});
$("#singleParentPick").onclick=()=>openPicker(p=>{selected.parent=p;renderOffspring()});
$("#treePick").onclick=()=>openPicker(p=>{selected.tree=p;treeSelections.clear();renderTree()});
$("#swapParents").onclick=()=>{[selected.a,selected.b]=[selected.b,selected.a];renderParents()};
$("#clearParents").onclick=()=>{selected.a=selected.b=null;renderParents()};
$("#copyParents").onclick=async()=>{
 const r=getResults(selected.a,selected.b);if(!r.length)return toast("コピーする結果がありません");
 const text=r.map(x=>{
  const genderSpecific=x.parent1Gender!=="WILDCARD"||x.parent2Gender!=="WILDCARD";
  return `${x.first.jp} + ${x.second.jp} → ${x.child.jp}${genderSpecific?`（${x.note}）`:""}`;
 }).join("\n");
 try{
  if(!navigator.clipboard?.writeText)throw new Error("Clipboard API unavailable");
  await navigator.clipboard.writeText(text);toast("コピーしました");
 }catch{toast("クリップボードへコピーできませんでした")}
};
["targetFilter","targetSort"].forEach(id=>$("#"+id).addEventListener(id.endsWith("Filter")?"input":"change",renderTarget));
["offspringFilter","offspringSort"].forEach(id=>$("#"+id).addEventListener(id.endsWith("Filter")?"input":"change",renderOffspring));
["dexSearch","dexSort","dexVariant","dexElement","dexWork","dexWorkLevel"].forEach(id=>$("#"+id).addEventListener(id==="dexSearch"?"input":"change",renderDex));
$("#pickerClose").onclick=closePicker;$("#pickerModal").addEventListener("click",e=>{if(e.target===$("#pickerModal"))closePicker()});
["pickerSearch","pickerSort","pickerVariant","pickerElement","pickerWork","pickerLevel"].forEach(id=>$("#"+id).addEventListener(id==="pickerSearch"?"input":"change",renderPicker));
$("#pickerList").addEventListener("click",e=>{const b=e.target.closest("[data-id]");if(!b)return;const p=byId.get(b.dataset.id);const cb=pickerCallback;closePicker();cb?.(p)});
document.querySelector(".seg").addEventListener("click",e=>{const b=e.target.closest("[data-orient]");if(!b)return;treeOrientation=b.dataset.orient;document.querySelectorAll("[data-orient]").forEach(x=>x.classList.toggle("active",x===b));treeSelections.clear();renderTree()});
$("#treeDepth").onchange=()=>{treeSelections.clear();renderTree()};
$("#treeCanvas").addEventListener("click",e=>{const b=e.target.closest("[data-nav]");if(!b)return;const path=b.dataset.nav,d=+b.dataset.d;const old=treeSelections.get(path)||0;treeSelections.set(path,Math.max(0,old+d));renderTree()});
$("#zoomIn").onclick=()=>{zoom=Math.min(2,zoom+.15);applyTreeTransform()};
$("#zoomOut").onclick=()=>{zoom=Math.max(.3,zoom-.15);applyTreeTransform()};
$("#zoomReset").onclick=()=>{zoom=1;panX=panY=0;applyTreeTransform()};
const vp=$("#treeViewport");let dragging=false,lastX=0,lastY=0,pointers=new Map(),pinchDist=0;
vp.addEventListener("pointerdown",e=>{vp.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});dragging=true;lastX=e.clientX;lastY=e.clientY});
vp.addEventListener("pointermove",e=>{
 if(!pointers.has(e.pointerId))return;pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
 if(pointers.size===2){const a=[...pointers.values()],d=Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y);if(pinchDist)zoom=Math.max(.3,Math.min(2,zoom*d/pinchDist));pinchDist=d;applyTreeTransform();return}
 if(dragging){panX+=e.clientX-lastX;panY+=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;applyTreeTransform()}
});
function endPointer(e){pointers.delete(e.pointerId);dragging=pointers.size>0;pinchDist=0}
vp.addEventListener("pointerup",endPointer);vp.addEventListener("pointercancel",endPointer);
vp.addEventListener("wheel",e=>{e.preventDefault();zoom=Math.max(.3,Math.min(2,zoom+(e.deltaY<0?.1:-.1)));applyTreeTransform()},{passive:false});
document.addEventListener("keydown",e=>{if(e.key==="Escape")closePicker()});

updateHowto("parents");
void load();
