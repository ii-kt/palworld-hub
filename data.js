"use strict";

const APP_DATASET_ID="pw-1.0.1.100619-24181105-cad80fe15c38";
const APP_DATA_SCHEMA_VERSION=2;
const EXPECTED_GAME_VERSION="v1.0.1.100619";
const EXPECTED_CLIENT_APP_ID="1623730";
const EXPECTED_CLIENT_BUILD_ID="24181527";
const EXPECTED_SERVER_APP_ID="2394010";
const EXPECTED_SERVER_BUILD_ID="24181105";
const EXPECTED_SERVER_DEPOT_MANIFEST_ID="2167164727892555341";
const EXPECTED_SERVER_PAK_SHA256="cad80fe15c38d74a795779fbab31f04bc2c15c37fb8a2188e4d89f3800fb0e68";
const EXPECTED_MAPPINGS_SHA256="561ef13c8ee3cf785e4de8aa5bc9b3ad1646e416d895f1d1166fa27ebdfd26b0";
const EXPECTED_CATALOG_CONTENT_HASH="872e4a79af5b5043ee97d9a4287a41bba407afc96ff3b0a6de56fff827d334b3";
const EXPECTED_RAW_ASSET_SHA256="e23a12ceffae5792b69c8faebe8ee3fbacbc09f0bd88572410d2b3b59aca1fe0";
const EXPECTED_NATIVE_EVIDENCE_SHA256="ac079224cbadb33886092145de2d4f5e2d6da6ccc5ba4cb0374f1e2f552e2651";
const EXPECTED_NATIVE_RUNTIME_EVIDENCE_SHA256="265bf315873f9d4f1e58ac8fec9544b912e7e6cea304cdc3b34cb1437be63bb1";
const EXPECTED_NATIVE_RUNTIME_EVIDENCE_DIGEST="08d7850d2bb566a77cd8734c93b7ed8f31563c287850e41450de2328c89a36a6";
const EXPECTED_SERVER_EXECUTABLE_SHA256="788649fa1592160faa7bcf07ccd16d474ebeaae954717bc32284b5a43028d8e7";
const EXPECTED_PAL_DATA_SHA256="77b300c10a1225f51e1c218ada7d03d236cc9fcb8b950ab79fa25a5b0e67fdf0";
const EXPECTED_BREEDING_DATA_SHA256="74f2ac2b7825ff9e4f0cea7426c0d22e701d53eb250ad78d2b2b28979dadc52c";
const EXPECTED_GENERATED_DATA_SHA256="d00bdc6286be2e0a53227fb7ceb677d79a13717ca2ae5bb4930cfcec3b275cb7";
const DATA_VERSION=encodeURIComponent(APP_DATASET_ID);
const DATA_URLS={
 pals:`data/pals.verified.json?dataset=${DATA_VERSION}`,
 breeding:`data/breeding.verified.json?dataset=${DATA_VERSION}`,
 verification:`data/verification.json?dataset=${DATA_VERSION}`
};

const ELEMENT_JP={Neutral:"無",Fire:"炎",Water:"水",Electric:"雷",Grass:"草",Dark:"闇",Dragon:"竜",Ground:"地",Ice:"氷"};
const WORK_JP={emitflame:"火おこし",watering:"水やり",seeding:"種まき",generateelectricity:"発電",handcraft:"手作業",collection:"採集",deforest:"伐採",mining:"採掘",oilextraction:"原油抽出",productmedicine:"製薬",cool:"冷却",transport:"運搬",monsterfarm:"牧場"};

let pals=[],byName=new Map(),byCode=new Map(),byId=new Map(),pairMap=new Map(),parentsByChild=new Map(),offspringByParent=new Map();
let selected={a:null,b:null,target:null,parent:null,tree:null};
let pickerCallback=null,treeOrientation="result",treeSelections=new Map();
let zoom=1,panX=0,panY=0;
let verification=null,lastDataError=null;

const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pairKey=(a,b)=>[a,b].sort().join("|");
const palSort=(a,b)=>a.no-b.no||String(a.suffix||"").localeCompare(String(b.suffix||""))||a.sourceOrder-b.sourceOrder||a.index-b.index;

async function fetchDocument(url,timeout=30000){
 const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),timeout);
 try{
  const response=await fetch(url,{cache:"no-store",headers:{"Cache-Control":"no-cache"},signal:ctrl.signal});
  if(!response.ok)throw new Error(`${response.status} ${url}`);
  const text=await response.text();
  let value;
  try{value=JSON.parse(text)}catch{throw new Error(`JSONが破損しています: ${url}`)}
  return {value,text};
 }finally{clearTimeout(timer)}
}
async function sha256Hex(text){
 const bytes=new TextEncoder().encode(text),digest=await crypto.subtle.digest("SHA-256",bytes);
 return [...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,"0")).join("");
}
function assertHeader(value,schema,label){
 if(!value||value.schemaVersion!==schema)throw new Error(`${label}のスキーマがアプリと一致しません`);
 if(value.datasetId!==APP_DATASET_ID)throw new Error(`${label}のデータセットがアプリと一致しません`);
 if(value.gameVersion!==EXPECTED_GAME_VERSION||value.targetServerBuildId!==EXPECTED_SERVER_BUILD_ID)throw new Error(`${label}の対象ビルドがアプリと一致しません`);
}

function genderMark(value){return value==="MALE"?"♂":value==="FEMALE"?"♀":""}
function normalizedResultSignature(first,second,child,gender1,gender2){
 const a={uid:first.uid,gender:gender1},b={uid:second.uid,gender:gender2};
 const [left,right]=a.uid<=b.uid?[a,b]:[b,a];
 return [left.uid,left.gender,right.uid,right.gender,child.uid].join("|");
}
function triangularIndex(size,first,second){
 if(first>second)[first,second]=[second,first];
 return first*size-first*(first-1)/2+(second-first);
}
function clearData(){
 pals=[];byName.clear();byCode.clear();byId.clear();pairMap.clear();parentsByChild.clear();offspringByParent.clear();
 selected={a:null,b:null,target:null,parent:null,tree:null};treeSelections.clear();verification=null;
}
function preparePals(payload,compact){
 assertHeader(payload,2,"パル一覧");
 if(!Array.isArray(payload.pals)||!Array.isArray(compact.palOrder))throw new Error("パル一覧の形式が不正です");
 if(payload.pals.length!==288)throw new Error(`パル一覧の件数が不正です: ${payload.pals.length}/288`);
 pals=payload.pals.map((raw,index)=>({
  ...raw,
  id:String(raw.id||"").toLowerCase(),
  code:String(raw.id||"").toLowerCase(),
  uid:String(raw.id||"").toLowerCase(),
  index,
  sourceOrder:Number(raw.sourceOrder),
  no:Number(raw.no),
  suffix:String(raw.suffix||""),
  variant:Boolean(raw.variant),
  power:Number(raw.power),
  elements:Array.isArray(raw.elements)?raw.elements:[],
  work:raw.work&&typeof raw.work==="object"?raw.work:{}
 }));
 if(pals.some(p=>!p.id||!p.en||!p.jp||!Number.isInteger(p.no)||p.no<=0||!Number.isInteger(p.power)||p.power<=0||!Number.isInteger(p.sourceOrder)||!p.elements.length||p.variant!==Boolean(p.suffix)||!p.isPal||p.isBoss||p.isRaidBoss||p.isTowerBoss))throw new Error("パル情報に欠落または未公開データがあります");
 const order=pals.map(p=>p.id);
 if(order.length!==compact.palOrder.length||order.some((id,index)=>id!==String(compact.palOrder[index]).toLowerCase()))throw new Error("パル順序と配合表が一致しません");
 pals.forEach(p=>{
  if(byId.has(p.uid))throw new Error(`パルIDが重複しています: ${p.uid}`);
  byId.set(p.uid,p);byCode.set(p.code,p);if(!byName.has(p.en.toLowerCase()))byName.set(p.en.toLowerCase(),p);
 });
}
function addResult(first,second,child,parent1Gender="WILDCARD",parent2Gender="WILDCARD"){
 if(!first||!second||!child)throw new Error("配合結果の参照先が不正です");
 if(![parent1Gender,parent2Gender].every(value=>["WILDCARD","FEMALE","MALE"].includes(value)))throw new Error("性別条件が不正です");
 const key=pairKey(first.uid,second.uid);
 if(!pairMap.has(key))pairMap.set(key,[]);
 const genderSpecific=parent1Gender!=="WILDCARD"||parent2Gender!=="WILDCARD";
 const note=genderSpecific?`${first.jp}${genderMark(parent1Gender)} × ${second.jp}${genderMark(parent2Gender)} の場合`:"";
 const result={first,second,child,note,parent1Gender,parent2Gender};
 const signature=normalizedResultSignature(first,second,child,parent1Gender,parent2Gender);
 if(pairMap.get(key).some(existing=>normalizedResultSignature(existing.first,existing.second,existing.child,existing.parent1Gender,existing.parent2Gender)===signature))throw new Error(`配合結果が重複しています: ${key}`);
 pairMap.get(key).push(result);
}
function buildIndexes(compact){
 assertHeader(compact,3,"配合表");
 if(!Array.isArray(compact.children)||!Array.isArray(compact.genderOverrides))throw new Error("配合データの形式が不正です");
 const size=pals.length,expected=size*(size+1)/2;
 if(compact.children.length!==expected)throw new Error(`配合表が不完全です: ${compact.children.length}/${expected}組`);
 if(compact.children.some(child=>!Number.isInteger(child)||child<0||child>=size))throw new Error("配合表に不正な子パル番号があります");
 const overrides=new Map();
 for(const override of compact.genderOverrides){
  if(!Number.isInteger(override.pairIndex)||override.pairIndex<0||override.pairIndex>=expected||!Array.isArray(override.rows)||override.rows.length<2)throw new Error("性別依存データが不正です");
  if(overrides.has(override.pairIndex))throw new Error("性別依存ペアが重複しています");
  overrides.set(override.pairIndex,override);
 }
 let cursor=0;
 for(let firstIndex=0;firstIndex<size;firstIndex++){
  for(let secondIndex=firstIndex;secondIndex<size;secondIndex++,cursor++){
   if(cursor!==triangularIndex(size,firstIndex,secondIndex))throw new Error("配合表のインデックスが不正です");
   const override=overrides.get(cursor);
   if(override){
    if(override.pair?.[0]!==firstIndex||override.pair?.[1]!==secondIndex)throw new Error("性別依存ペアの位置が不正です");
    for(const row of override.rows){
     if(![row.parent1,row.parent2,row.child].every(value=>Number.isInteger(value)&&value>=0&&value<size))throw new Error("性別依存データの参照先が不正です");
     addResult(pals[row.parent1],pals[row.parent2],pals[row.child],row.parent1Gender,row.parent2Gender);
    }
   }else{
    const childIndex=compact.children[cursor];
    addResult(pals[firstIndex],pals[secondIndex],pals[childIndex]);
   }
  }
 }
 const offspringGroups=new Map();
 for(const results of pairMap.values()){
  results.sort((a,b)=>palSort(a.child,b.child)||a.note.localeCompare(b.note,"ja"));
  for(const result of results){
   if(!parentsByChild.has(result.child.uid))parentsByChild.set(result.child.uid,[]);
   parentsByChild.get(result.child.uid).push(result);
  }
  const first=results[0].first,second=results[0].second;
  for(const parent of first.uid===second.uid?[first]:[first,second]){
   if(!offspringGroups.has(parent.uid))offspringGroups.set(parent.uid,new Map());
   const partner=parent.uid===first.uid?second:first;
   offspringGroups.get(parent.uid).set(partner.uid,{partner,results:[...results]});
  }
 }
 for(const parent of pals)offspringByParent.set(parent.uid,[...(offspringGroups.get(parent.uid)?.values()||[])]);
}
function validateIndexes(compact,check){
 assertHeader(check,8,"検証情報");
 const expectedPairs=pals.length*(pals.length+1)/2;
  if(check.appDataSchemaVersion!==APP_DATA_SCHEMA_VERSION||check.status!=="fixed-build-native-runtime-matched"||check.gameVersion!==EXPECTED_GAME_VERSION||check.sourceClientAppId!==EXPECTED_CLIENT_APP_ID||check.sourceClientBuildId!==EXPECTED_CLIENT_BUILD_ID||check.targetServerAppId!==EXPECTED_SERVER_APP_ID||check.targetServerBuildId!==EXPECTED_SERVER_BUILD_ID||check.targetServerDepotManifestId!==EXPECTED_SERVER_DEPOT_MANIFEST_ID||check.serverPakSha256!==EXPECTED_SERVER_PAK_SHA256||check.mappingsUsmapSha256!==EXPECTED_MAPPINGS_SHA256||check.catalogContentHash!==EXPECTED_CATALOG_CONTENT_HASH||check.rawAssetExtractionSha256!==EXPECTED_RAW_ASSET_SHA256||check.nativeBreedingEvidenceSha256!==EXPECTED_NATIVE_EVIDENCE_SHA256||check.nativeRuntimeEvidenceSha256!==EXPECTED_NATIVE_RUNTIME_EVIDENCE_SHA256||check.nativeRuntimeEvidenceDigest!==EXPECTED_NATIVE_RUNTIME_EVIDENCE_DIGEST||check.serverExecutableSha256!==EXPECTED_SERVER_EXECUTABLE_SHA256||check.breedingItemEffectDataPath!=="Pal/Content/Pal/DataAsset/MapObject/Breeding/DA_BreedingItemEffectData"||JSON.stringify(check.breedingItemCombiRankBonusValues)!=="[0]"||check.palDataSha256!==EXPECTED_PAL_DATA_SHA256||check.breedingDataSha256!==EXPECTED_BREEDING_DATA_SHA256||check.generatedDataSha256!==EXPECTED_GENERATED_DATA_SHA256||check.palCount!==288||check.palCount!==pals.length||check.unorderedPairCount!==41616||check.unorderedPairCount!==expectedPairs||check.compactChildCount!==compact.children.length||check.resultRowCount!==41617||check.matchingResultRowCount!==41617||check.mismatchCount!==0||check.missingPairCount!==0||check.extraPairCount!==0||check.unreleasedPalContaminationCount!==0||check.duplicateCount!==0||check.exactGameAssetExtractionEvidence!==true||check.nativeBreedingStaticAnalysisEvidence!==true||check.nativeBreedingFunctionExhaustiveVerification!==true||check.nativeBreedingFunctionInvocationCount!==166464||check.nativeRuntimeMismatchCount!==0||check.nativeRuntimeFixedExtractedAssetTablesInjected!==true||check.nativeRuntimeLivePakDataTablesReadDirectly!==false||check.gameRuntimeHatchExhaustiveVerification!==false||check.resultScope!=="base-released-form-id"||check.bossAlphaSpeciesMappingVerified!==true||check.bossAlphaAndIndividualStatePostProcessingModeled!==false)throw new Error("検証情報と確定配合表が一致しません");
 if(pairMap.size!==expectedPairs)throw new Error(`配合表が不完全です: ${pairMap.size}/${expectedPairs}組`);
 const zeroParentIds=pals.filter(pal=>!parentsByChild.has(pal.uid)).map(pal=>pal.uid).sort();
 if(JSON.stringify(zeroParentIds)!==JSON.stringify(check.zeroParentCandidateChildIds)||parentsByChild.size!==pals.length-zeroParentIds.length)throw new Error(`逆引き表の0候補形態が検証情報と一致しません: ${zeroParentIds.join(",")}`);
 const logicalRows=[...pairMap.values()].reduce((sum,rows)=>sum+rows.length,0);
 if(logicalRows!==check.resultRowCount)throw new Error(`結果行数が不正です: ${logicalRows}/${check.resultRowCount}`);
 for(const [key,results] of pairMap){
  if(!results.length)throw new Error(`結果が空の配合ペアです: ${key}`);
  const seen=new Set();
  for(const result of results){
   const signature=normalizedResultSignature(result.first,result.second,result.child,result.parent1Gender,result.parent2Gender);
   if(seen.has(signature))throw new Error(`配合結果が重複しています: ${key}`);
   seen.add(signature);
   if(!(parentsByChild.get(result.child.uid)||[]).includes(result))throw new Error(`逆引き往復に失敗しました: ${key}`);
  }
 }
 for(const parent of pals){
  const groups=offspringByParent.get(parent.uid)||[];
  if(groups.length!==pals.length||new Set(groups.map(group=>group.partner.uid)).size!==pals.length)throw new Error(`親1体一覧が不完全です: ${parent.code}`);
  for(const group of groups){
   const forward=pairMap.get(pairKey(parent.uid,group.partner.uid))||[];
   if(group.results.length!==forward.length||group.results.some(result=>!forward.includes(result)))throw new Error(`親1体一覧の往復に失敗しました: ${parent.code}`);
  }
 }
 const genderPairs=[...pairMap].filter(([,rows])=>rows.some(result=>result.parent1Gender!=="WILDCARD"||result.parent2Gender!=="WILDCARD"));
 if(genderPairs.length!==1||genderPairs[0][0]!=="catmage|foxmage"||genderPairs[0][1].length!==2)throw new Error("性別依存配合が不完全です");
}
function setDataStatus(text,state="warn"){
 const status=$("#dataStatus");status.textContent=text;status.className=`badge ${state}`;status.style.cursor="default";status.onclick=null;
}
async function checkCurrentBuild(check){
 const freshness=$("#buildFreshness");
 const versionStatus=$("#versionStatus");
 try{
  const {value}=await fetchDocument(check.currentBuildEndpoint,10000);
  const current=String(value?.data?.[check.targetServerAppId]?.depots?.branches?.public?.buildid||"");
  if(!current)throw new Error("現行Build IDを取得できません");
  if(current!==check.targetServerBuildId){
   document.body.dataset.buildState="outdated";
   versionStatus.textContent="現在の対応バージョン";
   setDataStatus("新ビルド検出・旧固定ビルド（未検証）","warn");
   freshness.textContent=`現行サーバーBuild ${current}を検出しました。この表はBuild ${check.targetServerBuildId}用のため、現行版としては未検証です。`;
   freshness.hidden=false;
   return;
  }
  document.body.dataset.buildState="current";
  versionStatus.textContent="最新バージョンに対応しています";
   setDataStatus("対象サーバーBuild一致・資産表照合済み","ok");
  freshness.hidden=true;
 }catch{
  document.body.dataset.buildState="unknown";
  versionStatus.textContent="現在の対応バージョン";
  setDataStatus("固定ビルド資産表・現行ビルド確認不能","warn");
  freshness.textContent=`Build ${check.targetServerBuildId}の固定データは利用できますが、現行Build IDを確認できませんでした。`;
  freshness.hidden=false;
 }
}
function initialiseData(palPayload,compact,check){
 clearData();verification=check;preparePals(palPayload,compact);buildIndexes(compact);validateIndexes(compact,check);
 fillFilterOptions();
 document.body.dataset.dataState="ready";
 setDataStatus("固定ビルド資産表を機械照合済み","ok");
 $("#palCount").textContent=`${pals.length}形態`;
 $("#comboCount").textContent=`${pairMap.size.toLocaleString()}組`;
 $("#buildId").textContent=`Build ${check.targetServerBuildId}`;
 renderAll();
 void checkCurrentBuild(check);
}
async function load(){
 setDataStatus("配合データ読込中","warn");document.body.dataset.dataState="loading";lastDataError=null;
 try{
  const checkDocument=await fetchDocument(DATA_URLS.verification);
  const check=checkDocument.value;
  assertHeader(check,8,"検証情報");
  if(check.appDataSchemaVersion!==APP_DATA_SCHEMA_VERSION)throw new Error("アプリとデータのバージョンが一致しません");
  const [palDocument,compactDocument]=await Promise.all([fetchDocument(DATA_URLS.pals),fetchDocument(DATA_URLS.breeding)]);
  const [palHash,breedingHash]=await Promise.all([sha256Hex(palDocument.text),sha256Hex(compactDocument.text)]);
  if(palHash!==EXPECTED_PAL_DATA_SHA256||palHash!==check.palDataSha256||breedingHash!==EXPECTED_BREEDING_DATA_SHA256||breedingHash!==check.breedingDataSha256)throw new Error("配合データのSHA-256が検証情報と一致しません");
  initialiseData(palDocument.value,compactDocument.value,check);
 }catch(error){
  lastDataError=error instanceof Error?error:new Error(String(error));clearData();document.body.dataset.dataState="error";
  $("#palCount").textContent="0形態";$("#comboCount").textContent="読込失敗";$("#buildId").textContent="Build未確認";
  setDataStatus("データ検証失敗・タップで再試行","warn");
  $("#dataStatus").style.cursor="pointer";$("#dataStatus").onclick=()=>{void load()};
  renderAll();toast("確定配合データを検証できないため表示を停止しました");
 }
}

Object.defineProperty(window,"PalworldDataState",{get:()=>({
 datasetId:APP_DATASET_ID,palCount:pals.length,pairCount:pairMap.size,
 logicalRows:[...pairMap.values()].reduce((sum,rows)=>sum+rows.length,0),
 error:lastDataError?.message||null,
})});
