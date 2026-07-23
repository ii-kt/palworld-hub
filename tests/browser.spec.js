import {test,expect,devices} from "@playwright/test";
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import {fileURLToPath} from "node:url";

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const verification=JSON.parse(fs.readFileSync(path.join(ROOT,"data/verification.json"),"utf8"));
const SITE="/";

async function isolateExternalRequests(page,buildId="24181105"){
  await page.route("https://api.steamcmd.net/**",route=>route.fulfill({
    status:200,
    contentType:"application/json",
    body:JSON.stringify({status:"success",data:{"2394010":{depots:{branches:{public:{buildid:buildId}}}}}})
  }));
}

async function expectReady(page){
  await expect(page.locator("body")).toHaveAttribute("data-data-state","ready");
  await expect(page.locator("#palCount")).toHaveText("288形態");
  await expect(page.locator("#comboCount")).toHaveText("41,616組");
}

async function openReady(page){
  await page.goto(SITE);
  await expectReady(page);
}

async function selectPal(page,slot,id){
  await page.locator(slot).click();
  await expect(page.locator("#pickerModal")).toHaveClass(/open/);
  await page.locator("#pickerSearch").fill(id);
  await page.locator(`#pickerList [data-id="${id}"]`).click();
  await expect(page.locator("#pickerModal")).not.toHaveClass(/open/);
}

test.beforeEach(async({page})=>{
  await isolateExternalRequests(page);
});

test("01 desktop Chromium first load shows the fixed-build counts",async({page})=>{
  await openReady(page);
  await expect(page.locator("#buildId")).toHaveText("Build 24181105");
  await expect(page.locator("body")).toHaveAttribute("data-build-state","current");
  await expect(page.locator("#dataStatus")).toContainText("対象ビルド一致");
});

test("01b rendering is local and never requests third-party Pal images",async({page})=>{
  const thirdParty=[];
  page.on("request",request=>{
    if(/raw\.githubusercontent\.com|palcalc/i.test(request.url()))thirdParty.push(request.url());
  });
  await page.route("https://raw.githubusercontent.com/**",route=>route.abort("blockedbyclient"));
  await openReady(page);
  await page.locator('#tabs [data-tab="dex"]').click();
  await expect(page.locator("#dexGrid .palmark")).toHaveCount(288);
  await expect(page.locator(".palmark img")).toHaveCount(0);
  expect(thirdParty).toEqual([]);
});

test("02 reload reconstructs all indexes",async({page})=>{
  await openReady(page);
  await page.reload();
  await expect(page.locator("body")).toHaveAttribute("data-data-state","ready");
  const state=await page.evaluate(()=>window.PalworldDataState);
  expect(state).toMatchObject({palCount:288,pairCount:41616,logicalRows:41617,error:null});
});

test("03 a warm browser cache cannot retain a bad replacement table",async({page})=>{
  await openReady(page);
  const oldCachedPayload={schemaVersion:1,pals:Array.from({length:299},(_,index)=>({id:`old-${index}`}))};
  await page.route("**/data/pals.verified.json?**",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(oldCachedPayload)}));
  await page.reload();
  await expect(page.locator("body")).toHaveAttribute("data-data-state","error");
  await expect(page.locator("#palCount")).toHaveText("0形態");
  expect((await page.evaluate(()=>window.PalworldDataState)).error).toContain("SHA-256");
});

test("04 cache purge still loads the versioned dataset",async({page,context})=>{
  await openReady(page);
  await context.clearCookies();
  const session=await context.newCDPSession(page);
  await session.send("Network.enable");
  await session.send("Network.clearBrowserCache");
  const urls=[];
  page.on("request",request=>{if(request.url().includes("/data/")&&request.url().includes("dataset="))urls.push(request.url())});
  await page.reload();
  await expect(page.locator("body")).toHaveAttribute("data-data-state","ready");
  expect(urls).toHaveLength(3);
  expect(urls.every(url=>url.includes("dataset=pw-1.0.1.100619-24181105-cad80fe15c38"))).toBe(true);
});

test("05 JSON fetch failure fails closed",async({page})=>{
  const pattern="**/data/verification.json?**";
  await page.route(pattern,route=>route.fulfill({status:503,body:"unavailable"}));
  await page.goto(SITE);
  await expect(page.locator("body")).toHaveAttribute("data-data-state","error");
  await expect(page.locator("#comboCount")).toHaveText("読込失敗");
  expect(await page.evaluate(()=>window.PalworldDataState.pairCount)).toBe(0);
  await page.unroute(pattern);
  await page.locator("#dataStatus").click();
  await expectReady(page);
});

test("06 corrupt JSON fails closed",async({page})=>{
  const pattern="**/data/pals.verified.json?**";
  await page.route(pattern,route=>route.fulfill({status:200,contentType:"application/json",body:"not-json"}));
  await page.goto(SITE);
  await expect(page.locator("body")).toHaveAttribute("data-data-state","error");
  await expect(page.locator("#dataStatus")).toContainText("データ検証失敗");
  expect((await page.evaluate(()=>window.PalworldDataState)).error).toContain("JSONが破損");
  await page.unroute(pattern);
  await page.locator("#dataStatus").click();
  await expectReady(page);
});

test("07 schema or app-data version mismatch fails closed",async({page})=>{
  const wrong={...verification,schemaVersion:999,appDataSchemaVersion:999};
  await page.route("**/data/verification.json?**",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(wrong)}));
  await page.goto(SITE);
  await expect(page.locator("body")).toHaveAttribute("data-data-state","error");
  expect((await page.evaluate(()=>window.PalworldDataState)).error).toContain("スキーマ");
});

test("07b a replacement manifest cannot bless altered fixed-build data",async({page})=>{
  const altered=JSON.parse(fs.readFileSync(path.join(ROOT,"data/pals.verified.json"),"utf8"));
  altered.pals[0].jp="改変データ";
  const body=JSON.stringify(altered);
  const wrong={...verification,palDataSha256:crypto.createHash("sha256").update(body).digest("hex")};
  await page.route("**/data/verification.json?**",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(wrong)}));
  await page.route("**/data/pals.verified.json?**",route=>route.fulfill({status:200,contentType:"application/json",body}));
  await page.goto(SITE);
  await expect(page.locator("body")).toHaveAttribute("data-data-state","error");
  expect((await page.evaluate(()=>window.PalworldDataState)).error).toContain("SHA-256");
});

test("08 Japanese-name search filters the Pal list",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="dex"]').click();
  await page.locator("#dexSearch").fill("モコロン");
  await expect(page.locator("#dexGrid .pal-card")).toHaveCount(1);
  await expect(page.locator("#dexGrid")).toContainText("Lamball");
});

test("09 English-name search filters the Pal list",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="dex"]').click();
  await page.locator("#dexSearch").fill("Katress Ignis");
  await expect(page.locator("#dexGrid .pal-card")).toHaveCount(1);
  await expect(page.locator("#dexGrid")).toContainText("クレメーナ");
});

test("09b exact form IDs disambiguate and find the two Gumoss forms",async({page})=>{
  await openReady(page);
  await page.locator("#parentA").click();
  await page.locator("#pickerSearch").fill("ナエモチ");
  await expect(page.locator("#pickerList .picker-item")).toHaveCount(2);
  await expect(page.locator('#pickerList [data-id="plantslime"] .form-id')).toHaveText("形態ID PlantSlime");
  await expect(page.locator('#pickerList [data-id="plantslime_flower"] .form-id')).toHaveText("形態ID PlantSlime_Flower");
  await page.locator("#pickerSearch").fill("PlantSlime_Flower");
  await expect(page.locator("#pickerList .picker-item")).toHaveCount(1);
  await expect(page.locator('#pickerList [data-id="plantslime_flower"]')).toContainText("ナエモチ");
});

test("09c Pal-list and picker filters honor aptitude presence and levels through 8",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="dex"]').click();
  await page.locator("#dexWork").selectOption("mining");
  await expect(page.locator("#dexCount")).toHaveText("57形態");
  await expect(page.locator("#dexGrid .pal-card")).toHaveCount(57);
  await page.locator("#dexWorkLevel").selectOption("8");
  await expect(page.locator("#dexCount")).toHaveText("1形態");
  await expect(page.locator('#dexGrid [data-id="domearmordragon"]')).toContainText("採掘Lv.8");
  await page.locator("#dexWorkLevel").selectOption("0");
  await page.locator("#dexWork").selectOption("");
  await page.locator("#dexVariant").selectOption("variant");
  await expect(page.locator("#dexCount")).toHaveText("84形態");
  await page.locator("#dexVariant").selectOption("all");
  await page.locator("#dexElement").selectOption("Fire");
  await expect(page.locator("#dexCount")).toHaveText("43形態");

  await page.locator('#tabs [data-tab="parents"]').click();
  await page.locator("#parentA").click();
  await page.locator("#pickerWork").selectOption("mining");
  await expect(page.locator("#pickerList .picker-item")).toHaveCount(57);
  await page.locator("#pickerLevel").selectOption("8");
  await expect(page.locator("#pickerList .picker-item")).toHaveCount(1);
  await expect(page.locator('#pickerList [data-id="domearmordragon"]')).toContainText("DomeArmorDragon");
});

test("10 selecting two parents produces a child from the table",async({page})=>{
  await openReady(page);
  await selectPal(page,"#parentA","sheepball");
  await selectPal(page,"#parentB","chickenpal");
  await expect(page.locator("#childSlot .jpname")).toHaveText("チョロゾウ");
  await expect(page.locator("#childSlot .enname")).toHaveText("Teafant");
  await expect(page.locator("#childSlot .form-id")).toHaveText("形態ID Ganesha");
});

test("11 reversing parent order preserves the result",async({page})=>{
  await openReady(page);
  await selectPal(page,"#parentA","sheepball");
  await selectPal(page,"#parentB","chickenpal");
  const before=await page.locator("#childSlot").evaluate(element=>[...element.querySelectorAll(".jpname,.enname,.no")].map(node=>node.textContent));
  await page.locator("#swapParents").click();
  await expect.poll(()=>page.locator("#childSlot").evaluate(element=>[...element.querySelectorAll(".jpname,.enname,.no")].map(node=>node.textContent))).toEqual(before);
});

test("11b all 41,616 parent pairs are invariant under reversal",async({page})=>{
  await openReady(page);
  const checked=await page.evaluate(()=>{
    let count=0;
    for(let first=0;first<pals.length;first++){
      for(let second=first;second<pals.length;second++){
        const forward=getResults(pals[first],pals[second]);
        const reverse=getResults(pals[second],pals[first]);
        if(forward!==reverse||forward.length===0)throw new Error(`parent-order mismatch: ${pals[first].uid}|${pals[second].uid}`);
        count++;
      }
    }
    return count;
  });
  expect(checked).toBe(41616);
});

test("12 gender-dependent breeding displays both exact conditions",async({page})=>{
  await openReady(page);
  await selectPal(page,"#parentA","catmage");
  await selectPal(page,"#parentB","foxmage");
  await expect(page.locator("#parentResults .result-row")).toHaveCount(2);
  const dark=page.locator('#parentResults [data-child="foxmage_dark"]');
  const fire=page.locator('#parentResults [data-child="catmage_fire"]');
  await expect(dark).toContainText("フォレーオ");
  await expect(dark.locator(".note")).toHaveText("フォレーナ♀ × クレメーオ♂ の場合");
  await expect(fire).toContainText("クレメーナ");
  await expect(fire.locator(".note")).toHaveText("フォレーナ♂ × クレメーオ♀ の場合");
  await page.locator("#swapParents").click();
  await expect(page.locator("#parentA")).toContainText("フォレーナ");
  await expect(page.locator("#parentB")).toContainText("クレメーオ");
  await expect(page.locator('#parentResults [data-child="foxmage_dark"] .note')).toHaveText("フォレーナ♀ × クレメーオ♂ の場合");
  await expect(page.locator('#parentResults [data-child="catmage_fire"] .note')).toHaveText("フォレーナ♂ × クレメーオ♀ の場合");
});

test("13 copied result retains both gender conditions",async({page,context})=>{
  await context.grantPermissions(["clipboard-read","clipboard-write"],{origin:"http://127.0.0.1:4173"});
  await openReady(page);
  await selectPal(page,"#parentA","catmage");
  await selectPal(page,"#parentB","foxmage");
  await page.locator("#swapParents").click();
  await page.locator("#copyParents").click();
  await expect(page.locator("#toast")).toContainText("コピーしました");
  const copied=(await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,"\n");
  expect(copied).toBe([
    "フォレーナ [FoxMage] + クレメーオ [CatMage] → フォレーオ [FoxMage_Dark]（フォレーナ♀ × クレメーオ♂ の場合）",
    "フォレーナ [FoxMage] + クレメーオ [CatMage] → クレメーナ [CatMage_Fire]（フォレーナ♂ × クレメーオ♀ の場合）"
  ].join("\n"));
});

test("14 child-to-parent tab roundtrips its rows",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="target"]').click();
  await expect(page.locator("#view-target")).toBeVisible();
  await selectPal(page,"#targetPick","sheepball");
  await expect(page.locator('#targetResults [data-child="sheepball"]')).not.toHaveCount(0);
  await expect(page.locator("#targetCount")).toContainText("組");
});

test("14b child-to-parent shows an honest empty result for native zero-candidate forms",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="target"]').click();
  for(const id of ["kingwhale","plantslime_flower"]){
    await selectPal(page,"#targetPick",id);
    await expect(page.locator("#targetCount")).toHaveText("0組");
    await expect(page.locator("#targetResults .result-row")).toHaveCount(0);
    await expect(page.locator("#targetResults")).toContainText("該当する親候補がありません");
    await expect(page.locator("#targetPick .form-id")).toContainText(id==="kingwhale"?"KingWhale":"PlantSlime_Flower");
  }
});

test("15 single-parent list has 288 unique partners and groups gender outcomes",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="offspring"]').click();
  await selectPal(page,"#singleParentPick","catmage");
  await expect(page.locator("#offspringCount")).toHaveText("288組");
  await expect(page.locator("#offspringResults .result-row")).toHaveCount(288);
  const genderGroup=page.locator('#offspringResults [data-pair="catmage|foxmage"]');
  await expect(genderGroup).toHaveCount(1);
  await expect(genderGroup.locator(".offspring-option")).toHaveCount(2);
});

test("16 four-generation tree stops safely and retains gender labels",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="tree"]').click();
  await selectPal(page,"#treePick","catmage_fire");
  await page.locator("#treeDepth").selectOption("4");
  await expect(page.locator("#treeCanvas .tree-node")).not.toHaveCount(0);
  await expect(page.locator("#treeCanvas")).toContainText("必要性別");
  expect(await page.locator("#treeCanvas .tree-node").count()).toBeLessThanOrEqual(31);
});

test("16b parent-start tree supports depth, candidate navigation, and zoom controls",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="tree"]').click();
  await selectPal(page,"#treePick","catmage");
  await page.locator('[data-orient="parent"]').click();
  await expect(page.locator('[data-orient="parent"]')).toHaveClass(/active/);
  await page.locator("#treeDepth").selectOption("1");
  await expect(page.locator("#treeCanvas .tree-node")).toHaveCount(3);
  const rootNav=page.locator('#treeCanvas [data-nav="d"]').first();
  await expect(rootNav.locator("xpath=..").locator("span")).toContainText("1 /");
  await page.locator('#treeCanvas [data-nav="d"][data-d="1"]').first().click();
  await expect(page.locator('#treeCanvas [data-nav="d"]').first().locator("xpath=..").locator("span")).toContainText("2 /");
  await page.locator("#zoomIn").click();
  await expect(page.locator("#treeCanvas")).toHaveCSS("transform",/matrix\(1\.15/);
  await page.locator("#zoomReset").click();
  await expect(page.locator("#treeCanvas")).toHaveCSS("transform","matrix(1, 0, 0, 1, 0, 0)");
  await page.locator("#treeDepth").selectOption("4");
  expect(await page.locator("#treeCanvas .tree-node").count()).toBeGreaterThan(3);
});

const iphone13=devices["iPhone 13"];
test.describe("iPhone 13 emulation on Chromium",()=>{
  test.use({
    viewport:iphone13.viewport,
    screen:iphone13.screen,
    userAgent:iphone13.userAgent,
    deviceScaleFactor:iphone13.deviceScaleFactor,
    isMobile:iphone13.isMobile,
    hasTouch:iphone13.hasTouch
  });

  test("17 all main views remain operable without page overflow or console errors",async({page})=>{
    const errors=[];
    page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});
    page.on("pageerror",error=>errors.push(error.message));
    const expectNoPageOverflow=async()=>{
      const widths=await page.evaluate(()=>({
        viewport:document.documentElement.clientWidth,
        scroll:document.documentElement.scrollWidth
      }));
      expect(widths.scroll).toBeLessThanOrEqual(widths.viewport+1);
    };

    await openReady(page);
    expect(await page.evaluate(()=>({
      touch:navigator.maxTouchPoints,
      ratio:devicePixelRatio,
      userAgent:navigator.userAgent
    }))).toMatchObject({touch:1,ratio:3});
    expect(await page.evaluate(()=>navigator.userAgent)).toContain("iPhone");
    await expectNoPageOverflow();

    await selectPal(page,"#parentA","sheepball");
    await selectPal(page,"#parentB","chickenpal");
    await expect(page.locator("#childSlot")).toContainText("チョロゾウ");
    await expectNoPageOverflow();

    await page.locator('#tabs [data-tab="target"]').click();
    await selectPal(page,"#targetPick","kingwhale");
    await expect(page.locator("#targetCount")).toHaveText("0組");
    await expectNoPageOverflow();

    await page.locator('#tabs [data-tab="offspring"]').click();
    await selectPal(page,"#singleParentPick","sheepball");
    await expect(page.locator("#offspringCount")).toHaveText("288組");
    await expectNoPageOverflow();

    await page.locator('#tabs [data-tab="tree"]').click();
    await selectPal(page,"#treePick","catmage_fire");
    await page.locator("#treeDepth").selectOption("2");
    await expect(page.locator("#treeCanvas .tree-node")).not.toHaveCount(0);
    await expectNoPageOverflow();

    await page.locator('#tabs [data-tab="dex"]').click();
    await page.locator("#dexSearch").fill("Katress Ignis");
    await expect(page.locator("#dexGrid .pal-card")).toHaveCount(1);
    await expectNoPageOverflow();
    await page.waitForTimeout(100);
    expect(errors).toEqual([]);
  });
});

test("18 normal desktop feature flow has zero console or page errors",async({page})=>{
  const errors=[];
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});
  page.on("pageerror",error=>errors.push(error.message));
  await openReady(page);
  await selectPal(page,"#parentA","catmage");
  await selectPal(page,"#parentB","foxmage");
  for(const tab of ["target","offspring","tree","dex","parents"]){
    await page.locator(`#tabs [data-tab="${tab}"]`).click();
  }
  await page.waitForTimeout(250);
  expect(errors).toEqual([]);
});

test("19 a newly detected public build automatically removes current-build status",async({page})=>{
  await page.unroute("https://api.steamcmd.net/**");
  await page.route("https://api.steamcmd.net/**",route=>route.fulfill({
    status:200,
    contentType:"application/json",
    body:JSON.stringify({status:"success",data:{"2394010":{depots:{branches:{public:{buildid:"99999999"}}}}}})
  }));
  await openReady(page);
  await expect(page.locator("body")).toHaveAttribute("data-build-state","outdated");
  await expect(page.locator("#dataStatus")).toContainText("新ビルド検出");
  await expect(page.locator("#buildFreshness")).toContainText("現行サーバーBuild 99999999");
});

test("20 child-to-parent renders every candidate without a hidden display cap",async({page})=>{
  await openReady(page);
  await page.locator('#tabs [data-tab="target"]').click();
  await selectPal(page,"#targetPick","catvampire");
  await expect(page.locator("#targetCount")).toHaveText("1,181組");
  await expect(page.locator("#targetResults .result-row")).toHaveCount(1181);
});

test("21 build lookup failure keeps fixed data usable but removes current-build status",async({page})=>{
  await page.unroute("https://api.steamcmd.net/**");
  await page.route("https://api.steamcmd.net/**",route=>route.fulfill({status:503,body:"unavailable"}));
  await openReady(page);
  await expect(page.locator("body")).toHaveAttribute("data-build-state","unknown");
  await expect(page.locator("#dataStatus")).toContainText("現行ビルド確認不能");
  await expect(page.locator("#palCount")).toHaveText("288形態");
});

test("22 every reverse, single-parent, and tree candidate is backed by the same table",async({page})=>{
  await openReady(page);
  const audit=await page.evaluate(()=>{
    const signature=result=>normalizedResultSignature(
      result.first,result.second,result.child,result.parent1Gender,result.parent2Gender
    );
    const source=new Set([...pairMap.values()].flatMap(rows=>rows.map(signature)));
    let reverseRows=0,parentRows=0,ancestorRows=0,descendantRows=0;
    for(const pal of pals){
      for(const result of parentsByChild.get(pal.uid)||[]){
        if(!source.has(signature(result))||result.child.uid!==pal.uid)throw new Error(`invalid reverse row: ${pal.uid}`);
        reverseRows++;
      }
      const groups=offspringByParent.get(pal.uid)||[];
      if(groups.length!==pals.length)throw new Error(`incomplete single-parent index: ${pal.uid}`);
      for(const group of groups){
        for(const result of group.results){
          if(!source.has(signature(result)))throw new Error(`invalid single-parent row: ${pal.uid}`);
          parentRows++;
        }
      }
      for(const result of orderedAncestorPairs(pal)){
        if(!source.has(signature(result))||result.child.uid!==pal.uid)throw new Error(`invalid ancestor edge: ${pal.uid}`);
        ancestorRows++;
      }
      for(const result of orderedDescendantPairs(pal)){
        if(!source.has(signature(result)))throw new Error(`invalid descendant edge: ${pal.uid}`);
        descendantRows++;
      }
    }
    return {sourceRows:source.size,reverseRows,parentRows,ancestorRows,descendantRows};
  });
  expect(audit).toEqual({
    sourceRows:41617,
    reverseRows:41617,
    parentRows:82946,
    ancestorRows:41617,
    descendantRows:82946
  });
});
