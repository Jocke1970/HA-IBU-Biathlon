#!/usr/bin/env node
// Minimal HA custom element / visual editor smoke-test; no npm deps.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const root = path.resolve(__dirname,"..");
const content = fs.readFileSync(path.join(root,"dist/HA-IBU-Biathlon.js"),"utf8");
const registry = new Map();
class Element {
  attachShadow(){this.shadowRoot={innerHTML:"",querySelectorAll:()=>[]};return this.shadowRoot;}
  dispatchEvent(e){this.lastEvent=e;return true;}
}
const customElements={get:k=>registry.get(k),define:(k,v)=>registry.set(k,v)};
const window={customCards:[]};
const document={createElement:name=>{
  const Klass=registry.get(name);if(!Klass)throw Error("Unknown element: "+name);
  return new Klass();
}};
class CustomEvent {constructor(type,options){this.type=type;this.detail=options.detail;}}
const requests=[];
const fetch=(url)=>{requests.push(url);return Promise.resolve({
  ok:true,json:async()=>({
    at:"2026-11-15T12:08:50", backend_type:"offline_joined_replay",
    classes:{men:[{bib:101,name:"Idre Offline",nation:"SWE",
      status:"passed_checkpoint",last_checkpoint:{ipos:"5",elapsed_ms:455200}}]},
    shooting_range:[],sources:{results:{provider_name:"CCResult",live_verified:false},
    shooting:{provider_name:"CCResult",live_verified:false}},
    clocks:{results:{},shooting:{}}
  })});};
vm.runInNewContext(content,{HTMLElement:Element,customElements,window,document,CustomEvent,fetch});
const Card=registry.get("ha-ibu-biathlon-card");
const Editor=registry.get("ha-ibu-biathlon-card-editor");
assert.ok(Card&&Editor,"HA card and visual editor registered");
const stub=Card.getStubConfig();
assert.equal(stub.type,undefined,"HA getStubConfig must omit card type");
const editor=Card.getConfigElement();
assert.ok(editor instanceof Editor);
editor.setConfig({...stub});
editor.hass={language:"sv"};
assert.match(editor.shadowRoot.innerHTML,/Kortinställningar/);
const card=new Card();
card.setConfig({...stub,demo:true});
card.hass={language:"sv",states:{}};
assert.match(card.shadowRoot.innerHTML,/DEMO/);
assert.match(card.shadowRoot.innerHTML,/Axel Mannelqvist/);
assert.match(card.shadowRoot.innerHTML,/Skottserietid/);
assert.match(card.shadowRoot.innerHTML,/Senaste sträcka/);
assert.match(card.shadowRoot.innerHTML,/range-board/);
assert.match(card.shadowRoot.innerHTML,/Bana 3/);
assert.match(card.shadowRoot.innerHTML,/In på vallen/);
assert.match(card.shadowRoot.innerHTML,/Ut från vallen/);
assert.match(card.shadowRoot.innerHTML,/Mellan skotten/);
assert.match(card.shadowRoot.innerHTML,/Skottserietid/);
assert.match(card.shadowRoot.innerHTML,/Bana 1/);
assert.match(card.shadowRoot.innerHTML,/Banor: 30 \(antaget standardantal\)/);
assert.match(card.shadowRoot.innerHTML,/Bana 30/);
card.setConfig({...stub,demo:true,lane_count:12});
assert.match(card.shadowRoot.innerHTML,/Banor: 12/);
assert.match(card.shadowRoot.innerHTML,/Bana 12/);
assert.match(card.shadowRoot.innerHTML,/Bana 30/);
assert.match(card.shadowRoot.innerHTML,/range-row unavailable/);
assert.match(card.shadowRoot.innerHTML,/Bana 21<\/strong> · Ej tillgänglig/);
assert.match(card.shadowRoot.innerHTML,/Bana 13<\/strong> · Ej tillgänglig/);
assert.doesNotMatch(card.shadowRoot.innerHTML,/antaget standardantal/);
card.setConfig({...stub,demo:true});
assert.doesNotMatch(card.shadowRoot.innerHTML,/Ej tillgänglig/);
card.setConfig({...stub,demo:true,range_layout:"occupied"});
assert.doesNotMatch(card.shadowRoot.innerHTML,/Bana 12/);
assert.match(card.shadowRoot.innerHTML,/Bana 3/);
card.setConfig({...stub,demo:true,competition_name:"Sprint",competition_city:"Idre",competition_country:"Sverige"});
assert.match(card.shadowRoot.innerHTML,/Sprint/);
assert.match(card.shadowRoot.innerHTML,/Idre, Sverige/);

assert.match(card.shadowRoot.innerHTML,/CCResult/);
assert.match(card.shadowRoot.innerHTML,/container-type:inline-size/);
assert.match(card.shadowRoot.innerHTML,/@container \(max-width: 959px\)/);
assert.match(card.shadowRoot.innerHTML,/grid-template-columns:minmax\(0,1fr\) minmax\(0,1fr\)/);
assert.doesNotMatch(card.shadowRoot.innerHTML,/class="pill ">LIVE/);
card.setConfig({type:"custom:ha-ibu-biathlon-card",demo:false,entity:"sensor.biathlon"});
card.hass={language:"en",states:{
 "sensor.biathlon":{attributes:{livetiming:{
   at:"2026-11-15T12:08:50",classes:{men:[{bib:1,name:"<script>alert(1)</script>",
   status:"passed_checkpoint",last_checkpoint:null}]},shooting_range:[],
   sources:{results:{provider_name:"CCResult",live_verified:false},
            shooting:{provider_name:"CCResult",live_verified:false}}}
 }}
}};
assert.match(card.shadowRoot.innerHTML,/&lt;script&gt;/,"Athlete names escaped");
assert.doesNotMatch(card.shadowRoot.innerHTML,/<script>alert\(1\)<\/script>/);
assert.match(card.shadowRoot.innerHTML,/Results/);
assert.equal(window.customCards.length,1);
console.log("HA frontend smoke test: registration, editor, languages, demo, safe content OK");

async function testReplay(){
  const replayCard=new Card();
  replayCard.setConfig({replay_url:"/local/ibu/idre.json",demo:false});
  replayCard.hass={language:"sv",states:{}};
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,1);
  assert.equal(requests[0],"/local/ibu/idre.json");
  assert.match(replayCard.shadowRoot.innerHTML,/Idre Offline/);
  assert.match(replayCard.shadowRoot.innerHTML,/REPLAY/);
  assert.doesNotMatch(replayCard.shadowRoot.innerHTML,/LIVE<\/span>/);
  replayCard.setConfig({replay_url:"https://untrusted.example/replay.json",demo:false});
  assert.equal(requests.length,1,"No fetch for external source");
  assert.match(replayCard.shadowRoot.innerHTML,/Only \/local/);
  console.log("Local JSON fixture: loading, provenance and URL restriction OK");
}
testReplay().catch(e=>{console.error(e);process.exitCode=1;});
