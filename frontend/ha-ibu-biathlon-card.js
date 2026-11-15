import sv from "./translations/sv.js";
import en from "./translations/en.js";

const VERSION = "2026.11.0-dev.2";
const type = "custom:ha-ibu-biathlon-card";
const escapeHtml = (v) => String(v ?? "").replace(/[&<>"']/g, c => (
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const flag = (country) => {
  const codes = {SWE:"SE",NOR:"NO",FIN:"FI",EST:"EE",GER:"DE",FRA:"FR",
    ITA:"IT",AUT:"AT",SUI:"CH",USA:"US",CZE:"CZ",UKR:"UA"};
  const countryCode = codes[country];
  return countryCode ? String.fromCodePoint(...[...countryCode].map(c => c.charCodeAt(0) + 127397)) : "🏳️";
};
const timeOnly = value => {
  if (!value || typeof value !== "string") return "–";
  const match = value.match(/T(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : "–";
};
const elapsed = n => {
  if (typeof n !== "number" || !Number.isFinite(n)) return "–";
  const seconds = Math.floor(n / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")},${String(Math.floor(n % 1000 / 100))}`;
};
const DEMO = {
  backend_type:"offline_demo", at:"2026-11-15T12:08:50",
  sources: {
    results:{provider_name:"CCResult / EliteTiming", data_mode:"reconstructed_replay",
      last_recorded_receipt_local:null,live_verified:false},
    shooting:{provider_name:"CCResult / EliteTiming", data_mode:"observed_replay",
      last_recorded_receipt_local:"2026-11-15T12:08:46.910635",live_verified:false}
  },
  clocks: {
    results:{latest_event:{value_local:"2026-11-15T12:08:44",source_timezone_verified:false},
      latest_receipt:{value_local:null}},
    shooting:{latest_event:{value_local:"2026-11-15T12:08:15",source_timezone_verified:false},
      latest_receipt:{value_local:"2026-11-15T12:08:46.910635"}}
  },
  classes: {"36810_2854":[
    {athlete_id:"a",bib:101,name:"Axel Mannelqvist",nation:"SWE",
      display_status:"shooting_observed",last_checkpoint:{ipos:"5",elapsed_ms:455200,
      checkpoint_position:12,checkpoint_diff_ms:10000}},
    {athlete_id:"b",bib:102,name:"Johan Bergman",nation:"SWE",
      display_status:"passed_checkpoint",last_checkpoint:{ipos:"5",elapsed_ms:445200,
      checkpoint_position:8,checkpoint_diff_ms:0}}
  ]},
  shooting_range:[{athlete_id:"a",bib:101,class_id:"36810_2854",
    name:"Axel Mannelqvist",nation:"SWE",lane:3,shots_count:5,missed:2,
    shoot_string:"xoxoo",state:"active_unconfirmed",elapsed_on_range_seconds:34.921}]
};
const css = `
  :host {display:block;color:var(--primary-text-color);--biathlon-muted:var(--secondary-text-color)}
  ha-card {padding:16px;overflow:hidden}
  .head,.source-line,.rowline {display:flex;gap:10px;align-items:center;justify-content:space-between}
  .head h2 {font-size:1.12rem;margin:0;font-weight:650}
  .pill {font-size:.65rem;letter-spacing:.04em;padding:4px 9px;border-radius:20px;background:var(--secondary-background-color);font-weight:650}
  .pill.demo {background:var(--warning-color,#d79b25);color:#171717}
  .source-line {margin:10px 0;color:var(--biathlon-muted);font-size:.82rem}
  .panels {display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:12px}
  .panels.stacked,.panels.compact {grid-template-columns:1fr}
  .panel {min-width:0;border:1px solid var(--divider-color);border-radius:12px;padding:12px}
  .panel h3 {margin:0 0 10px;font-size:.91rem}
  .entry {display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:6px;padding:8px 0;border-top:1px solid var(--divider-color);font-size:.84rem}
  .entry:first-of-type {border-top:0}
  .minor,.clock,.notice {font-size:.73rem;color:var(--biathlon-muted)}
  .notice {margin-top:10px}
  .shooting {margin:8px 0}
  .targets {display:flex;gap:5px;margin:8px 0}
  .target {width:18px;height:18px;border-radius:50%;border:1.5px solid var(--primary-text-color);box-sizing:border-box}
  .target.hit {background:var(--primary-text-color)}
  .target.miss {background:var(--error-color,#d14b4b);border-color:var(--error-color,#d14b4b)}
  details {margin-top:12px;color:var(--biathlon-muted);font-size:.78rem}
  details summary {cursor:pointer;padding:5px 0}
  .error {padding:14px;text-align:center;color:var(--biathlon-muted)}
  @media(max-width:650px){.panels{grid-template-columns:1fr}}
`;
const defaults = {type,layout:"two_column",clock_display:"both",show_flags:true,
  source_details:"compact",show_version:true,demo:false,replay_url:""};
const validReplayUrl = url => typeof url === "string" &&
  /^\/local\/[a-zA-Z0-9/_-]+\.json(?:\?v=[a-zA-Z0-9._-]+)?$/.test(url);

class IbuBiathlonCard extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});this._config={...defaults};
    this._replayData=null;this._replayError=null;this._replayLoading=false;
    this._loadedUrl=null;this._requestId=0;}
  setConfig(config){
    if (!config || (config.type && config.type !== type)) throw Error("Invalid card type");
    const previous=this._config?.replay_url;
    this._config={...defaults,...config};
    if (previous !== this._config.replay_url) {
      this._replayData=null;this._loadedUrl=null;this._replayError=null;
    }
    this._startReplayLoad();
    this.render();
  }
  set hass(hass){this._hass=hass;this._startReplayLoad();this.render();}
  connectedCallback(){this._startReplayLoad();}
  disconnectedCallback(){this._requestId++;}
  _startReplayLoad(){
    const url=this._config?.replay_url;
    if (!url || this._config?.demo || this._replayLoading || this._loadedUrl===url) return;
    if (!validReplayUrl(url)){
      this._replayError="Only /local/*.json files can be loaded";
      this._loadedUrl=url;return;
    }
    this._replayLoading=true;this._replayError=null;
    const request=++this._requestId;
    fetch(url,{credentials:"same-origin",cache:"no-store"}).then(response=>{
      if (!response.ok) throw Error("HTTP "+response.status);
      return response.json();
    }).then(data=>{
      if (!data || typeof data!=="object" || !data.classes ||
          !Array.isArray(data.shooting_range) || !data.sources || !data.clocks)
        throw Error("Invalid combined replay JSON");
      if (request!==this._requestId || url!==this._config.replay_url) return;
      this._replayData=data;this._loadedUrl=url;
    }).catch(error=>{
      if (request!==this._requestId || url!==this._config.replay_url) return;
      this._replayError=String(error.message||error);
      this._loadedUrl=url;
    }).finally(()=>{
      if (request!==this._requestId || url!==this._config.replay_url) return;
      this._replayLoading=false;this.render();
    });
  }
  getCardSize(){return 5;}
  getGridOptions(){return {columns:12,rows:5,min_rows:3};}
  lang(){return this._hass?.language?.startsWith("sv") ? sv : en;}
  snapshot(){
    if (this._config.demo) return DEMO;
    if (this._config.replay_url) return this._replayData;
    const attrs=this._hass?.states?.[this._config.entity]?.attributes;
    let data=attrs?.livetiming;
    if (typeof data==="string"){try{data=JSON.parse(data);}catch{return null;}}
    return data && typeof data==="object" ? data : null;
  }
  render(){
    if (!this.shadowRoot) return;
    const t=this.lang(),config=this._config,data=this.snapshot();
    const isDemo=!!config.demo;
    const classes=data?.classes || {};
    const classId=config.class_id && classes[config.class_id] ? config.class_id:Object.keys(classes)[0];
    const people=(classes[classId] || []).slice().sort((a,b)=>{
      if(config.result_sort==="checkpoint_rank"){
        const pa=a.last_checkpoint,pb=b.last_checkpoint;
        if(pa?.ipos && pa.ipos===pb?.ipos)
          return (pa.checkpoint_position??99999)-(pb.checkpoint_position??99999);
      }
      return (a.bib??99999)-(b.bib??99999);
    });
    const range=(data?.shooting_range||[]).filter(x=>!classId||x.class_id===classId).slice();
    if(config.range_sort==="lane")range.sort((a,b)=>(a.lane??999)-(b.lane??999));
    const sources=data?.sources||{};
    const clocks=data?.clocks||{};
    const showClock=(side)=>{
      const c=clocks[side]||{},mode=config.clock_display||"both",parts=[];
      if(mode==="event"||mode==="both")parts.push(`${t.event}: ${timeOnly(c.latest_event?.value_local)}`);
      if(mode==="receipt"||mode==="both")parts.push(`${t.receipt}: ${timeOnly(c.latest_receipt?.value_local)}`);
      return `<div class="clock">${parts.map(escapeHtml).join(" · ")}</div>`;
    };
    const sourceLine=(side)=>escapeHtml(sources[side]?.provider_name||t.unknown);
    const results=people.length ? people.map(p=>{
      const cp=p.last_checkpoint;
      const status=p.display_status||p.status||t.unknownStatus;
      const pos=cp?.checkpoint_position!=null?`#${cp.checkpoint_position} · `:"";
      return `<div class="entry"><div>
        <div>${config.show_flags?flag(p.nation)+" ":""}<strong>${escapeHtml(p.bib??"–")}</strong> ${escapeHtml(p.name||t.unknown)}</div>
        <div class="minor">${escapeHtml(cp?`${t.checkpoint} ${cp.ipos} · ${pos}${status}`:status)}</div>
      </div><div>${escapeHtml(cp?elapsed(cp.elapsed_ms):"–")}</div></div>`;
    }).join(""):`<div class="error">${escapeHtml(t.noData)}</div>`;
    const lanes=range.length?range.map(s=>{
      const pattern=typeof s.shoot_string==="string"?s.shoot_string.slice(0,5):"";
      const targets=[...pattern].map(x=>`<span class="target ${x==="x"?"miss":"hit"}"></span>`).join("");
      return `<div class="entry"><div>
        <div>${escapeHtml(t.lane)} ${escapeHtml(s.lane??"–")} · ${config.show_flags?flag(s.nation)+" ":""}${escapeHtml(s.name||"#"+s.bib)}</div>
        <div class="minor">${escapeHtml(s.shots_count??0)} ${escapeHtml(t.shots)}, ${escapeHtml(s.missed??0)} ${escapeHtml(t.misses)} · ${escapeHtml(s.state||"")}</div>
        <div class="targets">${targets}</div>
      </div><div>${typeof s.elapsed_on_range_seconds==="number"?escapeHtml(s.elapsed_on_range_seconds.toFixed(1)+" s"):"–"}</div></div>`;
    }).join(""):`<div class="error">${escapeHtml(t.noRange)}</div>`;
    const verified=data?.sources?.results?.live_verified && data?.sources?.shooting?.live_verified && !isDemo;
    const badge=isDemo?t.demoNotice:verified?t.live:data?t.replay:t.noData;
    const replayMessage=config.replay_url && !isDemo
      ? (this._replayError ? `<div class="error">${escapeHtml(t.replayLoadError)}: ${escapeHtml(this._replayError)}</div>`
        : this._replayLoading ? `<div class="notice">${escapeHtml(t.replayLoading)}</div>` : "") : "";
    const detail=`<details ${config.source_details==="expanded"?"open":""}><summary>${escapeHtml(t.source)}</summary>
      <div>${escapeHtml(t.results)}: ${sourceLine("results")} · ${escapeHtml(sources.results?.data_mode||t.unknown)}</div>
      <div>${escapeHtml(t.range)}: ${sourceLine("shooting")} · ${escapeHtml(sources.shooting?.data_mode||t.unknown)}</div>
      <div class="minor">${escapeHtml(t.noVerifiedRanking)}</div>
      <div class="minor">${escapeHtml(t.sourceUnverified)}</div></details>`;
    this.shadowRoot.innerHTML=`<style>${css}</style><ha-card>
      <div class="head"><h2>🎯 ${escapeHtml(t.title)}</h2><span class="pill ${isDemo?"demo":""}">${escapeHtml(badge)}</span></div>
      <div class="source-line"><span>${escapeHtml(t.source)}: ${sourceLine("results")}</span><span>${escapeHtml(classId||"")}</span></div>
      <div class="panels ${["stacked","compact"].includes(config.layout)?config.layout:""}">
      <section class="panel"><h3>${escapeHtml(t.results)}</h3>${showClock("results")}${results}</section>
      <section class="panel"><h3>${escapeHtml(t.range)}</h3>${showClock("shooting")}${lanes}</section>
      </div>${replayMessage}${detail}${config.show_version?`<div class="notice">${escapeHtml(t.version)} ${VERSION}</div>`:""}
    </ha-card>`;
  }
  static getConfigElement(){return document.createElement("ha-ibu-biathlon-card-editor");}
  static getStubConfig(){const {type: _type,...stub}=defaults;return {...stub,demo:true};}
}
class IbuBiathlonCardEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});}
  setConfig(config){this._config={...defaults,...config};this.render();}
  set hass(hass){this._hass=hass;this.render();}
  render(){
    if(!this.shadowRoot||!this._config)return;
    const t=this._hass?.language?.startsWith("sv")?sv:en;
    const fields=[
      ["entity",t.entity,"text"],["replay_url",t.replayFile,"text"],["class_id",t.classId,"text"],
      ["layout",t.layout,["two_column","stacked","compact"]],
      ["clock_display",t.timeMode,["both","event","receipt"]],
      ["range_sort","Range sort",["arrival","lane"]],
      ["source_details",t.sourceDetails,["compact","expanded"]],
      ["demo",t.demo,"checkbox"],["show_flags",t.showFlags,"checkbox"],
      ["show_version",t.showVersion,"checkbox"]
    ];
    this.shadowRoot.innerHTML=`<style>:host{display:block}label{display:block;margin:12px 0;font-size:14px}
      input,select{width:100%;box-sizing:border-box;padding:8px;margin-top:4px;border-radius:6px;
      background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}
      input[type=checkbox]{width:auto}</style><div><strong>${escapeHtml(t.settings)}</strong>${fields.map(([name,label,kind])=>
      `<label>${escapeHtml(label)}${Array.isArray(kind)?
      `<select data-key="${name}">${kind.map(value=>`<option value="${value}" ${this._config[name]===value?"selected":""}>${escapeHtml(value)}</option>`).join("")}</select>`:
      `<input data-key="${name}" type="${kind}" ${kind==="checkbox"?(this._config[name]?"checked":""):`value="${escapeHtml(this._config[name]||"")}"`}/>`}</label>`).join("")}</div>`;
    this.shadowRoot.querySelectorAll("[data-key]").forEach(el=>el.addEventListener("change",()=>{
      const name=el.dataset.key;
      this._config={...this._config,[name]:el.type==="checkbox"?el.checked:el.value};
      this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this._config},
        bubbles:true,composed:true}));
    }));
  }
}
if(!customElements.get("ha-ibu-biathlon-card"))
  customElements.define("ha-ibu-biathlon-card",IbuBiathlonCard);
if(!customElements.get("ha-ibu-biathlon-card-editor"))
  customElements.define("ha-ibu-biathlon-card-editor",IbuBiathlonCardEditor);
window.customCards=window.customCards||[];
if(!window.customCards.some(x=>x.type===type))
  window.customCards.push({type,name:"HA IBU Biathlon",description:"Biathlon timing and shooting range with visual editor"});
